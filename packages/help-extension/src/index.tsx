// Copyright (c) Jupyter Development Team.
// Distributed under the terms of the Modified BSD License.

import {
  JupyterFrontEnd,
  JupyterFrontEndPlugin,
} from '@jupyterlab/application';

import { Dialog, ICommandPalette } from '@jupyterlab/apputils';

import { IMainMenu } from '@jupyterlab/mainmenu';

import { ITranslator } from '@jupyterlab/translation';

import { jupyterIcon } from '@jupyter-notebook/ui-components';

import * as React from 'react';

from platform import python_version /* to print Python version it is running on */

/**
 * A list of resources to show in the help menu.
 */
const RESOURCES = [
  {
    text: 'About Jupyter',
    url: 'https://jupyter.org',
  },
  {
    text: 'Markdown Reference',
    url: 'https://commonmark.org/help/',
  },
  {
    text: 'Documentation',
    url: 'https://jupyter-notebook.readthedocs.io/en/stable/',
  },
];

/**
 * The command IDs used by the help plugin.
 */
namespace CommandIDs {
  export const open = 'help:open';

  export const about = 'help:about';
}

/**
 * A plugin to open the about section with resources.
 */
const open: JupyterFrontEndPlugin<void> = {
  id: '@jupyter-notebook/help-extension:open',
  autoStart: true,
  description: 'A plugin to open the about section with resources',
  activate: (app: JupyterFrontEnd): void => {
    const { commands } = app;

    commands.addCommand(CommandIDs.open, {
      label: (args) => args['text'] as string,
      execute: (args) => {
        const url = args['url'] as string;
        window.open(url);
      },
    });
  },
};

/**
 * Plugin to add a command to show an About Jupyter Notebook and Markdown Reference.
 */
const about: JupyterFrontEndPlugin<void> = {
  id: '@jupyter-notebook/help-extension:about',
  autoStart: true,
  requires: [ITranslator],
  optional: [IMainMenu, ICommandPalette],
  description:
    'Plugin to add a command to show an About Jupyter Notebook and Markdown Reference',
  activate: (
    app: JupyterFrontEnd,
    translator: ITranslator,
    menu: IMainMenu | null,
    palette: ICommandPalette | null
  ): void => {
    const { commands } = app;
    const trans = translator.load('notebook');
    const category = trans.__('Help');

    commands.addCommand(CommandIDs.about, {
      label: trans.__('About %1', app.name),
      execute: () => {
        const title = (
          <>
            <span className="jp-AboutNotebook-header">
              <jupyterIcon.react width="196px" height="auto" />
            </span>
          </>
        );

        const notebookURL = 'https://github.com/jupyter/notebook';
        const contributorURL = 'https://github.com/jupyter/notebook/pulse';
        const aboutJupyter = trans.__('JUPYTER NOTEBOOK ON GITHUB');
        const contributorList = trans.__('CONTRIBUTOR LIST');
        const externalLinks = (
          <span>
            <a
              href={notebookURL}
              target="_blank"
              rel="noopener noreferrer"
              className="jp-Button-flat jp-AboutNotebook-about-externalLinks"
            >
              {aboutJupyter}
            </a>
            <a
              href={contributorURL}
              target="_blank"
              rel="noopener noreferrer"
              className="jp-Button-flat jp-AboutNotebook-about-externalLinks"
            >
              {contributorList}
            </a>
          </span>
        );
        const version = trans.__('Version: %1', app.version);
        const py_version = trans.__('Python version: %1', app.python_version());
        const copyright = trans.__('© 2021-2023 Jupyter Notebook Contributors');
        const body = (
          <>
            <span className="jp-AboutNotebook-version">{version}</span>
            <span className="jp-AboutNotebook-python-version">{py_version}</span>
            <div>{externalLinks}</div>
            <span className="jp-AboutNotebook-about-copyright">
              {copyright}
            </span>
          </>
        );

        const dialog = new Dialog({
          title,
          body,
          buttons: [
            Dialog.createButton({
              label: trans.__('Dismiss'),
              className:
                'jp-AboutNotebook-about-button jp-mod-reject jp-mod-styled',
            }),
          ],
        });
        dialog.addClass('jp-AboutNotebook');
        void dialog.launch();
      },
    });

    if (palette) {
      palette.addItem({ command: CommandIDs.about, category });
    }

    const resourcesGroup = RESOURCES.map((args) => ({
      args,
      command: CommandIDs.open,
    }));

    if (menu) {
      menu.helpMenu.addGroup(resourcesGroup, 30);
    }
  },
};

const plugins: JupyterFrontEndPlugin<any>[] = [open, about];

export default plugins;
