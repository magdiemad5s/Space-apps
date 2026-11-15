/** "HH:MM" in local time */
export function clockTime(d: Date): string {
  return d.toTimeString().slice(0, 5);
}

/** "HH:MM" -> minutes since midnight */
export function toMinutes(hhmm: string): number {
  const [h, m] = hhmm.split(":").map(Number);
  return h * 60 + m;
}

export function minutesOfDay(d: Date): number {
  return d.getHours() * 60 + d.getMinutes();
}
