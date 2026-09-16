import { render } from "@testing-library/react";
import type { ReactNode } from "react";
import { RefreshProvider } from "./RefreshContext";

export const renderInShell = (ui: ReactNode) => render(<RefreshProvider>{ui}</RefreshProvider>);
