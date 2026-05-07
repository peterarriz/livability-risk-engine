type ScoreDateInput = string | Date | null | undefined;

const SCORE_DATE_FORMATTER = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "numeric",
  year: "numeric",
});

const SCORE_MONTH_YEAR_FORMATTER = new Intl.DateTimeFormat("en-US", {
  month: "short",
  year: "numeric",
});

const ISO_DATE_PREFIX_RE = /^(\d{4})-(\d{2})-(\d{2})(?:\b|[T ])/;
const ISO_DATE_IN_TEXT_RE = /\b(\d{4}-\d{2}-\d{2})(?:[T ][0-9:.+\-Z]+)?\b/g;

export function parseScoreDate(value: ScoreDateInput): Date | null {
  if (!value) return null;
  if (value instanceof Date) {
    return Number.isNaN(value.getTime()) ? null : value;
  }

  const raw = value.trim();
  if (!raw) return null;

  const dateOnlyMatch = raw.match(ISO_DATE_PREFIX_RE);
  if (dateOnlyMatch) {
    const year = Number(dateOnlyMatch[1]);
    const month = Number(dateOnlyMatch[2]);
    const day = Number(dateOnlyMatch[3]);
    const date = new Date(year, month - 1, day, 12, 0, 0, 0);

    if (
      date.getFullYear() !== year ||
      date.getMonth() !== month - 1 ||
      date.getDate() !== day
    ) {
      return null;
    }

    return date;
  }

  const parsed = new Date(raw);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

export function formatScoreDate(value: ScoreDateInput): string | null {
  const date = parseScoreDate(value);
  return date ? SCORE_DATE_FORMATTER.format(date) : null;
}

export function formatScoreMonthYear(value: ScoreDateInput): string | null {
  const date = parseScoreDate(value);
  return date ? SCORE_MONTH_YEAR_FORMATTER.format(date) : null;
}

export function isFutureOrTodayScoreDate(value: ScoreDateInput): boolean {
  const date = parseScoreDate(value);
  if (!date) return false;

  const dateStart = new Date(date);
  dateStart.setHours(0, 0, 0, 0);
  const todayStart = new Date();
  todayStart.setHours(0, 0, 0, 0);
  return dateStart.getTime() >= todayStart.getTime();
}

export function formatScoreDateRange(
  start: ScoreDateInput,
  end: ScoreDateInput,
): string {
  const startLabel = formatScoreDate(start);
  const endLabel = formatScoreDate(end);

  if (startLabel && endLabel) return `${startLabel} - ${endLabel}`;
  if (startLabel) return `From ${startLabel}`;
  if (endLabel) return `Until ${endLabel}`;
  return "Dates unknown";
}

export function formatIsoDatesInText(text: string | null | undefined): string {
  if (!text) return text ?? "";
  return text.replace(ISO_DATE_IN_TEXT_RE, (value) => formatScoreDate(value) ?? value);
}
