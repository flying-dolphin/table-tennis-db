type ScheduleSidePrimaryLabelInput = {
  isTeamMatch: boolean;
  teamCode: string | null;
  playerNames: string[];
  placeholderText: string | null;
};

function placeholderLabel(placeholderText: string | null) {
  if (!placeholderText) return null;
  return placeholderText.toUpperCase() === "BYE" ? "轮空" : placeholderText;
}

export function scheduleSidePrimaryLabel({
  isTeamMatch,
  teamCode,
  playerNames,
  placeholderText,
}: ScheduleSidePrimaryLabelInput) {
  if (isTeamMatch) {
    if (teamCode) return teamCode.toUpperCase() === "BYE" ? "轮空" : teamCode;
    return placeholderLabel(placeholderText) ?? "待定";
  }

  if (playerNames.length > 0) return playerNames.join(" / ");
  return placeholderLabel(placeholderText) ?? teamCode ?? "待定";
}
