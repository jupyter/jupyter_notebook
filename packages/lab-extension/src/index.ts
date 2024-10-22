// Copyright (c) Jupyter Development Team.
// Distributed under the terms of the Modified BSD License.

import {
  ILabShell,
  JupyterFrontEnd,
  JupyterFrontEndPlugin,
} from '@jupyterlab/application';

import { ICommandPalette, IToolbarWidgetRegistry } from '@jupyterlab/apputils';

import { PageConfig, URLExt } from '@jupyterlab/coreutils';

import { INotebookTracker, NotebookPanel } from '@jupyterlab/notebook';

import { ITranslator } from '@jupyterlab/translation';

import { Menu, MenuBar, Widget } from '@lumino/widgets';

import {
  defaultNotebookPathOpener,
  INotebookPathOpener,
  INotebookShell,
} from '@jupyter-notebook/application';

import {
  caretDownIcon,
  CommandToolbarButton,
  launchIcon,
} from '@jupyterlab/ui-components';

/**
 * The command IDs used by the application plugin
 */
namespace CommandIDs {
  /**
   * Launch Jupyter Notebook Tree
   */
  export const launchNotebookTree = 'jupyter-notebook:launch-tree';

  /**
   * Open Jupyter Notebook
   */
  export const openNotebook = 'jupyter-notebook:open-notebook';

  /**
   * Open in JupyterLab
   */
  export const openLab = 'jupyter-notebook:open-lab';

  /**
   * Open in NbClassic
   */
  export const openNbClassic = 'jupyter-notebook:open-nbclassic';
}

interface ISwitcherChoice {
  command: string;
  commandLabel: string;
  commandDescription: string;
  buttonLabel: string;
  urlPrefix: string;
}

/**
 * A plugin to add custom toolbar items to the notebook page
 */
const interfaceSwitcher: JupyterFrontEndPlugin<void> = {
  id: '@jupyter-notebook/lab-extension:interface-switcher',
  description: 'A plugin to add custom toolbar items to the notebook page.',
  autoStart: true,
  requires: [ITranslator, INotebookTracker],
  optional: [
    ICommandPalette,
    INotebookPathOpener,
    INotebookShell,
    ILabShell,
    IToolbarWidgetRegistry,
  ],
  activate: (
    app: JupyterFrontEnd,
    translator: ITranslator,
    notebookTracker: INotebookTracker,
    palette: ICommandPalette | null,
    notebookPathOpener: INotebookPathOpener | null,
    notebookShell: INotebookShell | null,
    labShell: ILabShell | null,
    toolbarRegistry: IToolbarWidgetRegistry | null
  ) => {
    const { commands, shell } = app;
    const baseUrl = PageConfig.getBaseUrl();
    const trans = translator.load('notebook');
    const nbClassicEnabled =
      PageConfig.getOption('nbclassic_enabled') === 'true';
    const switcher = new Menu({ commands });
    const switcherOptions: ISwitcherChoice[] = [];
    const opener = notebookPathOpener ?? defaultNotebookPathOpener;

    if (!notebookShell) {
      switcherOptions.push({
        command: CommandIDs.openNotebook,
        commandLabel: trans.__('Notebook'),
        commandDescription: trans.__('Open in %1', 'Jupyter Notebook'),
        buttonLabel: 'openNotebook',
        urlPrefix: `${baseUrl}tree`,
      });
    }

    if (!labShell) {
      switcherOptions.push({
        command: CommandIDs.openLab,
        commandLabel: trans.__('JupyterLab'),
        commandDescription: trans.__('Open in %1', 'JupyterLab'),
        buttonLabel: 'openLab',
        urlPrefix: `${baseUrl}doc/tree`,
      });
    }

    if (nbClassicEnabled) {
      switcherOptions.push({
        command: CommandIDs.openNbClassic,
        commandLabel: trans.__('NbClassic'),
        commandDescription: trans.__('Open in %1', 'NbClassic'),
        buttonLabel: 'openNbClassic',
        urlPrefix: `${baseUrl}nbclassic/notebooks`,
      });
    }

    const isEnabled = () => {
      return (
        notebookTracker.currentWidget !== null &&
        notebookTracker.currentWidget === shell.currentWidget
      );
    };

    const addSwitcherCommand = (option: ISwitcherChoice) => {
      const { command, commandLabel, commandDescription, urlPrefix } = option;

      const execute = () => {
        const current = notebookTracker.currentWidget;
        if (!current) {
          return;
        }
        opener.open({
          prefix: urlPrefix,
          path: current.context.path,
        });
      };

      commands.addCommand(command, {
        label: (args) => {
          args.noLabel ? '' : commandLabel;
          if (args.isMenu || args.isPalette) {
            return commandDescription;
          }
          return commandLabel;
        },
        caption: commandLabel,
        execute,
        isEnabled,
      });

      if (palette) {
        palette.addItem({
          command,
          category: 'Other',
          args: { isPalette: true },
        });
      }
    };

    switcherOptions.forEach((option) => {
      const { command } = option;
      addSwitcherCommand(option);
      switcher.addItem({ command });
    });

    let toolbarFactory: (panel: NotebookPanel) => Widget;
    if (switcherOptions.length === 1) {
      toolbarFactory = (panel: NotebookPanel) => {
        const toolbarButton = new CommandToolbarButton({
          commands,
          id: switcherOptions[0].command,
          label: switcherOptions[0].commandLabel,
          icon: launchIcon,
        });
        toolbarButton.addClass('jp-nb-interface-switcher-button');
        return toolbarButton;
      };
    } else {
      const overflowOptions = {
        overflowMenuOptions: { isVisible: false },
      };
      const menubar = new MenuBar(overflowOptions);
      switcher.title.label = trans.__('Open in...');
      switcher.title.icon = caretDownIcon;
      menubar.addMenu(switcher);

      toolbarFactory = (panel: NotebookPanel) => {
        const menubar = new MenuBar(overflowOptions);
        menubar.addMenu(switcher);
        menubar.addClass('jp-InterfaceSwitcher');
        return menubar;
      };
    }

    if (toolbarRegistry) {
      toolbarRegistry.addFactory<NotebookPanel>(
        'Notebook',
        'interfaceSwitcher',
        toolbarFactory
      );
    }
  },
};

/**
 * A plugin to add a command to open the Jupyter Notebook Tree.
 */
const launchNotebookTree: JupyterFrontEndPlugin<void> = {
  id: '@jupyter-notebook/lab-extension:launch-tree',
  description: 'A plugin to add a command to open the Jupyter Notebook Tree.',
  autoStart: true,
  requires: [ITranslator],
  optional: [ICommandPalette],
  activate: (
    app: JupyterFrontEnd,
    translator: ITranslator,
    palette: ICommandPalette | null
  ): void => {
    const { commands } = app;
    const trans = translator.load('notebook');
    const category = trans.__('Help');

    commands.addCommand(CommandIDs.launchNotebookTree, {
      label: trans.__('Launch Jupyter Notebook File Browser'),
      execute: () => {
        const url = URLExt.join(PageConfig.getBaseUrl(), 'tree');
        window.open(url);
      },
    });

    if (palette) {
      palette.addItem({ command: CommandIDs.launchNotebookTree, category });
    }
  },
};

/**
 * Export the plugins as default.
 */
const plugins: JupyterFrontEndPlugin<any>[] = [
  launchNotebookTree,
  interfaceSwitcher,
];

export default plugins;
