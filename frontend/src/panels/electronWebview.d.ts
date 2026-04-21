// Electron's <webview> tag is not part of the standard HTML element set.
// When we're running inside the Electron kiosk host (see kiosk/ at the
// repo root), the main process enables webviewTag and the preload exposes
// a hosakaBrowserAdapter that flips the WebPanel into native-webview mode.
// These declarations give us enough types to use <webview> from JSX
// without pulling in all of Electron's renderer typings.

import type { DetailedHTMLProps, HTMLAttributes } from "react";

interface ElectronWebviewAttributes
  extends HTMLAttributes<HTMLElement> {
  src?: string;
  partition?: string;
  allowpopups?: string | boolean;
  useragent?: string;
  httpreferrer?: string;
  disablewebsecurity?: string | boolean;
  preload?: string;
}

declare module "react" {
  namespace JSX {
    interface IntrinsicElements {
      webview: DetailedHTMLProps<ElectronWebviewAttributes, HTMLElement>;
    }
  }
}

export {};
