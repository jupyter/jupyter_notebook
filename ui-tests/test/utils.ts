import { IJupyterLabPageFixture } from '@jupyterlab/galata';

import { Page } from '@playwright/test';

/**
 * Run the selected cell and advance.
 */
export async function runAndAdvance(
  page: IJupyterLabPageFixture | Page
): Promise<void> {
  await page.keyboard.press('Shift+Enter');
}
/** akshitha added a commnet here*/
/**
 * Wait for the kernel to be ready
 */
export async function waitForKernelReady(page: Page): Promise<void> {
  await page.waitForSelector('.jp-NotebookKernelStatus-fade');
  await page.waitForFunction(() => {
    const status = window.document.getElementsByClassName(
      'jp-NotebookKernelStatus'
    )[0];

    if (!status) {
      return false;
    }

    const finished = status?.getAnimations().reduce((prev, curr) => {
      return prev && curr.playState === 'finished';
    }, true);
    return finished;
  });
  const viewport = page.viewportSize();
  const width = viewport?.width;
  if (width && width > 600) {
    await page.waitForSelector('.jp-DebuggerBugButton[aria-disabled="false"]');
  }
}

/**
 * Special case for firefox headless issue
 * See https://github.com/jupyter/notebook/pull/6872#issuecomment-1549594166 for more details
 */
export async function hideAddCellButton(page: Page): Promise<void> {
  await page
    .locator('.jp-Notebook-footer')
    .evaluate((element) => (element.style.display = 'none'));
}

/**
 * Wait for the notebook to be ready
 */
export async function waitForNotebook(
  page: Page,
  browserName = ''
): Promise<void> {
  // wait for the kernel status animations to be finished
  await waitForKernelReady(page);
  await page.waitForSelector(
    ".jp-Notebook-ExecutionIndicator[data-status='idle']"
  );

  const checkpointLocator = '.jp-NotebookCheckpoint';
  // wait for the checkpoint indicator to be displayed
  await page.waitForSelector(checkpointLocator);

  // remove the amount of seconds manually since it might display strings such as "3 seconds ago"
  await page
    .locator(checkpointLocator)
    .evaluate(
      (element) => (element.innerHTML = 'Last Checkpoint: 3 seconds ago')
    );

  // special case for firefox headless issue
  // see https://github.com/jupyter/notebook/pull/6872#issuecomment-1549594166 for more details
  if (browserName === 'firefox') {
    await hideAddCellButton(page);
  }
}
