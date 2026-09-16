import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import App from "./shell/App";
import { RefreshProvider } from "./shell/RefreshContext";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <RefreshProvider>
      <App />
    </RefreshProvider>
  </StrictMode>,
);
