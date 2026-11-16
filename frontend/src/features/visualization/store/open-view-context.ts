"use client";

import { createContext, useContext } from "react";
import type { ViewConfig } from "../lib/config-schema";
import type { SavedView } from "../types";

/** The saved view the workbench was opened from, with its config as read. */
export type OpenView = { view: SavedView; config: ViewConfig; reload: () => void };

export const OpenViewContext = createContext<OpenView | null>(null);

/** The open saved view; null on a plain workbench (or outside one). */
export const useOpenView = () => useContext(OpenViewContext);
