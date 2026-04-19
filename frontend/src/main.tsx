import React, { Suspense } from "react";
import ReactDOM from "react-dom/client";
import { App } from "./App";
import "./i18n";
import "./styles/app.css";
import "@xterm/xterm/css/xterm.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <Suspense fallback="">
      <App />
    </Suspense>
  </React.StrictMode>,
);
