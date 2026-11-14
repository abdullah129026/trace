import { defineTheme } from "@astryxdesign/core/theme";

/* Flux Studio theme for Trace: the shared Astryx rollout tokens
   (workspace/user/files/astryx-rollout.md). Light glassy green surfaces,
   emerald accent only, status colors kept separate from brand. The accent
   seed drives the accent palette per scheme; the token overrides below
   seat the surfaces, text, borders, and status colors. */
export const fluxTheme = defineTheme({
  name: "flux",
  color: { accent: ["#047857", "#34D399"] },
  tokens: {
    "--color-background-body": ["#F2F7F2", "#0B100D"],
    "--color-background-surface": ["#FFFFFF", "#121915"],
    "--color-background-card": ["#FFFFFF", "#121915"],
    "--color-background-muted": ["#EAF2EA", "#182119"],
    "--color-border": ["#D9E6D9", "#243328"],
    "--color-border-emphasized": ["#D9E6D9", "#243328"],
    "--color-text-primary": ["#131F18", "#E8F1E9"],
    "--color-text-secondary": ["#50614E", "#9DB3A2"],
    "--color-text-disabled": ["#7E8F7E", "#6E8271"],
    "--color-icon-primary": ["#131F18", "#E8F1E9"],
    "--color-icon-secondary": ["#50614E", "#9DB3A2"],
    "--color-icon-disabled": ["#7E8F7E", "#6E8271"],
    "--color-accent-muted": ["#D9F5E5", "rgba(52,211,153,0.14)"],
    "--color-success": "#16A34A",
    "--color-warning": "#D97706",
    "--color-error": "#DC2626",
    "--color-info": "#0284C7",
    "--focus-outline-color": "#10B981",
  },
});
