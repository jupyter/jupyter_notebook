// Copyright (c) Jupyter Development Team.
// Distributed under the terms of the Modified BSD License.

import {
  IRouter,
  JupyterFrontEnd,
  JupyterFrontEndPlugin,
} from '@jupyterlab/application';

import { PageConfig, URLExt } from '@jupyterlab/coreutils';

import { ITerminalTracker } from '@jupyterlab/terminal';

import {
  INotebookPathOpener,
  defaultNotebookPathOpener,
} from '@jupyter-notebook/application';

import { find } from '@lumino/algorithm';

/**
 * A plugin to open terminals in a new tab
 */
const opener: JupyterFrontEndPlugin<void> = {
  id: '@jupyter-notebook/terminal-extension:opener',
  description: 'A plugin to open terminals in a new tab.',
  requires: [IRouter, ITerminalTracker],
  autoStart: true,
  activate: (
    app: JupyterFrontEnd,
    router: IRouter,
    tracker: ITerminalTracker
  ) => {
    const { commands } = app;
    const terminalPattern = new RegExp('/terminals/(.*)');
    const ignoreTreePattern = new RegExp('/(tree|notebooks|edit)/(.*)');

    const command = 'router:terminal';
    commands.addCommand(command, {
      execute: (args: any) => {
        const parsed = args as IRouter.ILocation;
        const matches = parsed.path.match(terminalPattern);
        const isTreeMatch = parsed.path.match(ignoreTreePattern);

        if (isTreeMatch || !matches) {
          return;
        }
        const [, name] = matches;
        if (!name) {
          return;
        }

        tracker.widgetAdded.connect((send, terminal) => {
          terminal.content.setOption('closeOnExit', false);
        });
        commands.execute('terminal:open', { name });
      },
    });

    router.register({ command, pattern: terminalPattern });
  },
};

/**
 * Open terminals in a new tab.
 */
const redirect: JupyterFrontEndPlugin<void> = {
  id: '@jupyter-notebook/terminal-extension:redirect',
  description: 'Open terminals in a new tab.',
  requires: [ITerminalTracker],
  optional: [INotebookPathOpener],
  autoStart: true,
  activate: (
    app: JupyterFrontEnd,
    tracker: ITerminalTracker,
    notebookPathOpener: INotebookPathOpener | null
  ) => {
    const baseUrl = PageConfig.getBaseUrl();
    const opener = notebookPathOpener ?? defaultNotebookPathOpener;

    tracker.widgetAdded.connect((send, terminal) => {
      const widget = find(
        app.shell.widgets('main'),
        (w) => w.id === terminal.id
      );
      if (widget) {
        // bail if the terminal is already added to the main area
        return;
      }
      const name = terminal.content.session.name;
      opener.open({
        prefix: URLExt.join(baseUrl, 'terminals'),
        path: name,
        target: '_blank',
      });

      // dispose the widget since it is not used on this page
      terminal.dispose();
    });
  },
};

/**
 * Export the plugins as default.
 */
const plugins: JupyterFrontEndPlugin<any>[] = [opener, redirect];

export default plugins;
