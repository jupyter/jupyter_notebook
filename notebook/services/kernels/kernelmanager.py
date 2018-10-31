"""A MultiKernelManager for use in the notebook webserver

- raises HTTPErrors
- creates REST API models
"""

# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.

from collections import defaultdict
from datetime import datetime, timedelta
from functools import partial
import os
import uuid

from tornado import gen, web
from tornado.concurrent import Future
from tornado.ioloop import IOLoop, PeriodicCallback

from jupyter_kernel_mgmt.client import IOLoopKernelClient
from jupyter_kernel_mgmt.restarter import TornadoKernelRestarter
from traitlets import (Any, Bool, Dict, List, Unicode, TraitError, Integer,
       Float, Instance, default, validate
)
from traitlets.config.configurable import LoggingConfigurable

from notebook.utils import to_os_path, exists
from notebook._tz import utcnow, isoformat
from ipython_genutils.py3compat import getcwd

from notebook.prometheus.metrics import KERNEL_CURRENTLY_RUNNING_TOTAL


class KernelInterface(LoggingConfigurable):
    def __init__(self, kernel_type, kernel_finder):
        super(KernelInterface, self).__init__()
        self.kernel_type = kernel_type
        self.kernel_finder = kernel_finder

        self.connection_info, self.manager = kernel_finder.launch(kernel_type)
        self.n_connections = 0
        self.execution_state = 'starting'
        self.last_activity = utcnow()

        self.restarter = TornadoKernelRestarter(self.manager, kernel_type,
                                           kernel_finder=self.kernel_finder)
        self.restarter.add_callback(self._handle_kernel_restarted, 'restart')
        self.restarter.start()

        self.buffer_for_key = None
        # TODO: the buffer should likely be a memory bounded queue, we're starting with a list to keep it simple
        self.buffer = []
        self.buffer_handlers = {}  # {channel: handler}

    client = None

    @gen.coroutine
    def connect_client(self):
        if self.client is not None:
            return self.client

        self.client = IOLoopKernelClient(self.connection_info, self.manager)
        yield self.client.wait_for_ready()
        return self.client

    @gen.coroutine
    def shutdown(self, now=False):
        if now:
            self.manager.kill()
        else:
            yield self.client.shutdown_or_terminate()
        self.client.close()
        self.manager.cleanup()
        self.stop_buffering()

    def interrupt(self):
        self.manager.interrupt()

    def _handle_kernel_restarted(self):
        self.manager = self.restarter.kernel_manager
        # TODO: connection_info
        self.connect_client()

    def start_buffering(self, session_key):
        # record the session key because only one session can buffer
        self.buffer_for_key = session_key

        # forward any future messages to the internal buffer
        def buffer_msg(channel, msg_parts):
            self.log.debug("Buffering msg on %s", channel)
            self.buffer.append((channel, msg_parts))

        for channel in ('shell', 'iopub', 'stdin'):
            handler = partial(buffer_msg, channel)
            self.client.add_handler(channel, handler)
            self.buffer_handlers[channel] = handler

    def get_buffer(self):
        """Get the buffer for a given kernel, and stop buffering new messages
        """
        buffer, key = self.buffer, self.buffer_for_key
        self.buffer = []
        self.stop_buffering()
        return buffer, key

    def stop_buffering(self):
        """Stop buffering kernel messages

        Parameters
        ----------
        kernel_id : str
            The id of the kernel to stop buffering.
        """
        # close buffering streams
        for channel, handler in self.buffer_handlers.items():
            try:
                self.client.remove_handler(channel, handler)
            except ValueError:
                pass   # Handler wasn't attached
        self.buffer_handlers = {}

        if self.buffer:
            self.log.info("Discarding %s buffered messages for %s",
                len(self.buffer), self.buffer_for_key)
        self.buffer = []
        self.buffer_for_key = None

class MappingKernelManager(LoggingConfigurable):
    """A KernelManager that handles notebook mapping and HTTP error handling"""

    @default('kernel_manager_class')
    def _default_kernel_manager_class(self):
        return "jupyter_client.ioloop.IOLoopKernelManager"

    default_kernel_name = Unicode('pyimport/kernel', config=True,
        help="The name of the default kernel to start"
    )

    root_dir = Unicode(config=True)
    
    _kernel_connections = Dict()

    _culler_callback = None

    _initialized_culler = False

    @default('root_dir')
    def _default_root_dir(self):
        try:
            return self.parent.notebook_dir
        except AttributeError:
            return getcwd()

    @validate('root_dir')
    def _update_root_dir(self, proposal):
        """Do a bit of validation of the root dir."""
        value = proposal['value']
        if not os.path.isabs(value):
            # If we receive a non-absolute path, make it absolute.
            value = os.path.abspath(value)
        if not exists(value) or not os.path.isdir(value):
            raise TraitError("kernel root dir %r is not a directory" % value)
        return value

    cull_idle_timeout = Integer(0, config=True,
        help="""Timeout (in seconds) after which a kernel is considered idle and ready to be culled.
        Values of 0 or lower disable culling. Very short timeouts may result in kernels being culled
        for users with poor network connections."""
    )

    cull_interval_default = 300 # 5 minutes
    cull_interval = Integer(cull_interval_default, config=True,
        help="""The interval (in seconds) on which to check for idle kernels exceeding the cull timeout value."""
    )

    cull_connected = Bool(False, config=True,
        help="""Whether to consider culling kernels which have one or more connections.
        Only effective if cull_idle_timeout > 0."""
    )

    cull_busy = Bool(False, config=True,
        help="""Whether to consider culling kernels which are busy.
        Only effective if cull_idle_timeout > 0."""
    )

    buffer_offline_messages = Bool(True, config=True,
        help="""Whether messages from kernels whose frontends have disconnected should be buffered in-memory.

        When True (default), messages are buffered and replayed on reconnect,
        avoiding lost messages due to interrupted connectivity.

        Disable if long-running kernels will produce too much output while
        no frontends are connected.
        """
    )
    
    kernel_info_timeout = Float(60, config=True,
        help="""Timeout for giving up on a kernel (in seconds).

        On starting and restarting kernels, we check whether the
        kernel is running and responsive by sending kernel_info_requests.
        This sets the timeout in seconds for how long the kernel can take
        before being presumed dead. 
        This affects the MappingKernelManager (which handles kernel restarts) 
        and the ZMQChannelsHandler (which handles the startup).
        """
    )

    _kernel_buffers = Any()
    @default('_kernel_buffers')
    def _default_kernel_buffers(self):
        return defaultdict(lambda: {'buffer': [], 'session_key': '', 'channels': {}})

    last_kernel_activity = Instance(datetime,
        help="The last activity on any kernel, including shutting down a kernel")

    def __init__(self, kernel_finder, **kwargs):
        super(MappingKernelManager, self).__init__(**kwargs)
        self.last_kernel_activity = utcnow()
        self._kernels = {}
        self._restarters = {}
        self.kernel_finder = kernel_finder

    def get_kernel(self, kernel_id):
        return self._kernels[kernel_id]

    #-------------------------------------------------------------------------
    # Methods for managing kernels and sessions
    #-------------------------------------------------------------------------

    def _handle_kernel_died(self, kernel_id):
        """notice that a kernel died"""
        self.log.warning("Kernel %s died, removing from map.", kernel_id)
        kernel = self._kernels.pop(kernel_id)
        kernel.client.close()
        kernel.manager.cleanup()

        KERNEL_CURRENTLY_RUNNING_TOTAL.labels(
            type=kernel.kernel_type
        ).inc()

    def cwd_for_path(self, path):
        """Turn API path into absolute OS path."""
        os_path = to_os_path(path, self.root_dir)
        # in the case of notebooks and kernels not being on the same filesystem,
        # walk up to root_dir if the paths don't exist
        while not os.path.isdir(os_path) and os_path != self.root_dir:
            os_path = os.path.dirname(os_path)
        return os_path

    @gen.coroutine
    def start_kernel(self, kernel_id=None, path=None, kernel_name=None, **kwargs):
        """Start a kernel for a session and return its kernel_id.

        Parameters
        ----------
        kernel_id : uuid
            The uuid to associate the new kernel with. If this
            is not None, this kernel will be persistent whenever it is
            requested.
        path : API path
            The API path (unicode, '/' delimited) for the cwd.
            Will be transformed to an OS path relative to root_dir.
        kernel_name : str
            The name identifying which kernel spec to launch. This is ignored if
            an existing kernel is returned, but it may be checked in the future.
        """
        if kernel_id is None:
            if path is not None:
                kwargs['cwd'] = self.cwd_for_path(path)
            kernel_id = str(uuid.uuid4())
            if kernel_name is None:
                kernel_name = 'pyimport/kernel'
            elif '/' not in kernel_name:
                kernel_name = 'spec/' + kernel_name

            yield self._start_kernel(kernel_id, kernel_name)

            # Increase the metric of number of kernels running
            # for the relevant kernel type by 1
            KERNEL_CURRENTLY_RUNNING_TOTAL.labels(
                type=self._kernels[kernel_id].kernel_type
            ).inc()

        else:
            self._check_kernel_id(kernel_id)
            self.log.info("Using existing kernel: %s" % kernel_id)

        # Initialize culling if not already
        if not self._initialized_culler:
            self.initialize_culler()

        # py2-compat
        raise gen.Return(kernel_id)

    @gen.coroutine
    def _start_kernel(self, kernel_id, kernel_type):
        kernel = KernelInterface(kernel_type, self.kernel_finder)
        yield kernel.connect_client()
        self._kernels[kernel_id] = kernel

        self.start_watching_activity(kernel_id)
        self.log.info("Kernel started: %s" % kernel_id)

        kernel.restarter.add_callback(
            lambda: self._handle_kernel_died(kernel_id),
            'dead'
        )

    def start_buffering(self, kernel_id, session_key, channels):
        """Start buffering messages for a kernel

        Parameters
        ----------
        kernel_id : str
            The id of the kernel to stop buffering.
        session_key: str
            The session_key, if any, that should get the buffer.
            If the session_key matches the current buffered session_key,
            the buffer will be returned.
        channels: dict({'channel': ZMQStream})
            The zmq channels whose messages should be buffered.
        """

        if not self.buffer_offline_messages:
            for channel, stream in channels.items():
                stream.close()
            return

        self.log.info("Starting buffering for %s", session_key)
        self._check_kernel_id(kernel_id)
        kernel = self._kernels[kernel_id]
        # clear previous buffering state
        kernel.stop_buffering()
        kernel.start_buffering(session_key)

    @gen.coroutine
    def _shutdown_all(self):
        futures = [self.shutdown_kernel(kid) for kid in self.list_kernel_ids()]
        yield gen.multi(futures)

    def shutdown_all(self):
        # Blocking function to call when the notebook server is shutting down
        loop = IOLoop.current()
        loop.run_sync(self._shutdown_all)

    @gen.coroutine
    def shutdown_kernel(self, kernel_id, now=False):
        """Shutdown a kernel by kernel_id"""
        self._check_kernel_id(kernel_id)
        kernel = self._kernels.pop(kernel_id)
        self.log.info("Shutting down kernel %s", kernel_id)
        yield kernel.shutdown()
        self.last_kernel_activity = utcnow()

        # Decrease the metric of number of kernels
        # running for the relevant kernel type by 1
        KERNEL_CURRENTLY_RUNNING_TOTAL.labels(
            type=kernel.kernel_type
        ).dec()

    @gen.coroutine
    def restart_kernel(self, kernel_id):
        """Restart a kernel by kernel_id"""
        self._check_kernel_id(kernel_id)
        kernel = self.get_kernel(kernel_id)

        yield kernel.shutdown()

        try:
            yield gen.with_timeout(
                timedelta(seconds=self.kernel_info_timeout),
                self._start_kernel(kernel_id, kernel.kernel_type)
            )
        except gen.TimeoutError:
            self.log.warning("Timeout waiting for kernel_info_reply: %s",
                             kernel_id)
            # Decrease the metric of number of kernels
            # running for the relevant kernel type by 1
            KERNEL_CURRENTLY_RUNNING_TOTAL.labels(
                type=kernel.kernel_type
            ).dec()
            raise gen.TimeoutError("Timeout waiting for restart")

    def notify_connect(self, kernel_id):
        """Notice a new connection to a kernel"""
        if kernel_id in self._kernels:
            self._kernels[kernel_id].n_connections += 1

    def notify_disconnect(self, kernel_id):
        """Notice a disconnection from a kernel"""
        if kernel_id in self._kernels:
            self._kernels[kernel_id].n_connections -= 1

    def kernel_model(self, kernel_id):
        """Return a JSON-safe dict representing a kernel

        For use in representing kernels in the JSON APIs.
        """
        self._check_kernel_id(kernel_id)
        kernel = self._kernels[kernel_id]

        model = {
            "id":kernel_id,
            "name": kernel.kernel_type,
            "last_activity": isoformat(kernel.last_activity),
            "execution_state": kernel.execution_state,
            "connections": self._kernels[kernel_id].n_connections,
        }
        return model

    def list_kernels(self):
        """Returns a list of models for kernels running."""
        kernels = []
        for kernel_id in self._kernels.keys():
            model = self.kernel_model(kernel_id)
            kernels.append(model)
        return kernels

    def list_kernel_ids(self):
        return list(self._kernels.keys())

    def __contains__(self, kernel_id):
        return kernel_id in self._kernels

    # override _check_kernel_id to raise 404 instead of KeyError
    def _check_kernel_id(self, kernel_id):
        """Check a that a kernel_id exists and raise 404 if not."""
        if kernel_id not in self:
            raise web.HTTPError(404, u'Kernel does not exist: %s' % kernel_id)

    # monitoring activity:

    def start_watching_activity(self, kernel_id):
        """Start watching IOPub messages on a kernel for activity.
        
        - update last_activity on every message
        - record execution_state from status messages
        """
        kernel = self._kernels[kernel_id]

        def record_activity(msg):
            """Record an IOPub message arriving from a kernel"""
            self.last_kernel_activity = kernel.last_activity = utcnow()

            msg_type = msg.header['msg_type']
            if msg_type == 'status':
                kernel.execution_state = msg.content['execution_state']
                self.log.debug("activity on %s: %s (%s)", kernel_id, msg_type, kernel.execution_state)
            else:
                self.log.debug("activity on %s: %s", kernel_id, msg_type)

        kernel.client.add_handler('iopub', record_activity)

    def initialize_culler(self):
        """Start idle culler if 'cull_idle_timeout' is greater than zero.

        Regardless of that value, set flag that we've been here.
        """
        if not self._initialized_culler and self.cull_idle_timeout > 0:
            if self._culler_callback is None:
                loop = IOLoop.current()
                if self.cull_interval <= 0: #handle case where user set invalid value
                    self.log.warning("Invalid value for 'cull_interval' detected (%s) - using default value (%s).",
                        self.cull_interval, self.cull_interval_default)
                    self.cull_interval = self.cull_interval_default
                self._culler_callback = PeriodicCallback(
                    self.cull_kernels, 1000*self.cull_interval)
                self.log.info("Culling kernels with idle durations > %s seconds at %s second intervals ...",
                    self.cull_idle_timeout, self.cull_interval)
                if self.cull_busy:
                    self.log.info("Culling kernels even if busy")
                if self.cull_connected:
                    self.log.info("Culling kernels even with connected clients")
                self._culler_callback.start()

        self._initialized_culler = True

    def cull_kernels(self):
        self.log.debug("Polling every %s seconds for kernels idle > %s seconds...",
            self.cull_interval, self.cull_idle_timeout)
        """Create a separate list of kernels to avoid conflicting updates while iterating"""
        for kernel_id in list(self._kernels):
            try:
                self.cull_kernel_if_idle(kernel_id)
            except Exception as e:
                self.log.exception("The following exception was encountered while checking the idle duration of kernel %s: %s",
                    kernel_id, e)

    def cull_kernel_if_idle(self, kernel_id):
        kernel = self._kernels[kernel_id]
        self.log.debug("kernel_id=%s, kernel_name=%s, last_activity=%s", kernel_id, kernel.kernel_name, kernel.last_activity)
        if kernel.last_activity is not None:
            dt_now = utcnow()
            dt_idle = dt_now - kernel.last_activity
            # Compute idle properties
            is_idle_time = dt_idle > timedelta(seconds=self.cull_idle_timeout)
            is_idle_execute = self.cull_busy or (kernel.execution_state != 'busy')
            connections = self._kernel_connections.get(kernel_id, 0)
            is_idle_connected = self.cull_connected or not connections
            # Cull the kernel if all three criteria are met
            if (is_idle_time and is_idle_execute and is_idle_connected):
                idle_duration = int(dt_idle.total_seconds())
                self.log.warning("Culling '%s' kernel '%s' (%s) with %d connections due to %s seconds of inactivity.",
                                 kernel.execution_state, kernel.kernel_type, kernel_id, connections, idle_duration)
                kernel.shutdown()
