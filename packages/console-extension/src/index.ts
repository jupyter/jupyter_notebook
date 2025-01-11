// Copyright (c) Jupyter Development Team.
// Distributed under the terms of the Modified BSD License.

import {
  IRouter,
  JupyterFrontEnd,
  JupyterFrontEndPlugin,
} from '@jupyterlab/application';

import { IConsoleTracker } from '@jupyterlab/console';

import { PageConfig, URLExt } from '@jupyterlab/coreutils';

import {
  INotebookPathOpener,
  defaultNotebookPathOpener,
} from '@jupyter-notebook/application';

import { find } from '@lumino/algorithm';

/**
 * A plugin to open consoles in a new tab
 */
const opener: JupyterFrontEndPlugin<void> = {
  id: '@jupyter-notebook/console-extension:opener',
  requires: [IRouter],
  autoStart: true,
  description: 'A plugin to open consoles in a new tab',
  activate: (app: JupyterFrontEnd, router: IRouter) => {
    const { commands } = app;
    const consolePattern = new RegExp('/consoles/(.*)');
    const ignoreTreePattern = new RegExp('/(tree|notebooks|edit)/(.*)');

    const command = 'router:console';
    commands.addCommand(command, {
      execute: (args: any) => {
        const parsed = args as IRouter.ILocation;
        const matches = parsed.path.match(consolePattern);
        const isTreeMatch = parsed.path.match(ignoreTreePattern);

        if (isTreeMatch || !matches) {
          return;
        }
        const [, match] = matches;
        if (!match) {
          return;
        }

        const path = decodeURIComponent(match);
        commands.execute('console:create', { path });
      },
    });

    router.register({ command, pattern: consolePattern });
  },
};

/**
 * Open consoles in a new tab.
 */
const redirect: JupyterFrontEndPlugin<void> = {
  id: '@jupyter-notebook/console-extension:redirect',
  requires: [IConsoleTracker],
  optional: [INotebookPathOpener],
  autoStart: true,
  description: 'Open consoles in a new tab',
  activate: (
    app: JupyterFrontEnd,
    tracker: IConsoleTracker,
    notebookPathOpener: INotebookPathOpener | null
  ) => {
    const baseUrl = PageConfig.getBaseUrl();
    const opener = notebookPathOpener ?? defaultNotebookPathOpener;

    tracker.widgetAdded.connect(async (send, console) => {
      const { sessionContext } = console;
      await sessionContext.ready;
      const widget = find(
        app.shell.widgets('main'),
        (w) => w.id === console.id
      );
      if (widget) {
        // bail if the console is already added to the main area
        return;
      }
      opener.open({
        prefix: URLExt.join(baseUrl, 'consoles'),
        path: sessionContext.path,
        target: '_blank',
      });

      // the widget is not needed anymore
      console.dispose();
    });
  },
};

/**
 * Export the plugins as default.
 */
const plugins: JupyterFrontEndPlugin<any>[] = [opener, redirect];

export default plugins;
