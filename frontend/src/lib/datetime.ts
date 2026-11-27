const IST_TIME_FORMATTER = new Intl.DateTimeFormat("en-IN", {
  timeZone: "Asia/Kolkata",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

export function formatIstTime(isoString: string): string {
  const date = new Date(isoString);
  if (Number.isNaN(date.getTime())) {
    return "--:--";
  }
  return IST_TIME_FORMATTER.format(date);
}

export function formatIstTimeWithZone(isoString: string): string {
  return `${formatIstTime(isoString)} IST`;
}

export function formatHoursOld(ageMinutes: number): string {
  const hours = Math.max(1, Math.floor(ageMinutes / 60));
  return hours === 1 ? "1 hour" : `${hours} hours`;
}
