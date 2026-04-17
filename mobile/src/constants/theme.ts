export const theme = {
  colors: {
    background: "#061424",
    backgroundAlt: "#0c2337",
    surface: "#10273d",
    surfaceMuted: "#18314b",
    border: "#355069",
    text: "#d6e3fa",
    textDim: "#9eb6d2",
    primary: "#f4631e",
    primarySoft: "#ffb599",
    danger: "#e74c3c",
    warning: "#e67e22",
    success: "#2ecc71",
    info: "#4ea8de",
  },
  spacing: {
    xs: 6,
    sm: 10,
    md: 14,
    lg: 20,
    xl: 28,
  },
  radius: {
    sm: 8,
    md: 12,
    lg: 16,
    pill: 999,
  },
};

export function riskColor(label: string): string {
  const normalized = label.toUpperCase();
  if (normalized === "LOW") {
    return theme.colors.success;
  }
  if (normalized === "MODERATE") {
    return "#f1c40f";
  }
  if (normalized === "HIGH") {
    return theme.colors.warning;
  }
  return theme.colors.danger;
}
