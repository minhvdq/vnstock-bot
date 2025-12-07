import { Time, UTCTimestamp } from "lightweight-charts";

// Parse time from various formats - preserve original time without timezone conversion
// Converts datetime strings to UTC timestamp treating the string as UTC (no timezone shift)
export const parseTime = (timeValue: string | number): Time => {
  if (timeValue == null) {
    console.warn("parseTime received null/undefined value");
    return Math.floor(Date.now() / 1000) as UTCTimestamp;
  }
  
  // If it's already a number, keep it as-is (assume it's already a timestamp in the correct format)
  if (typeof timeValue === "number") {
    // If it's in milliseconds (larger than a reasonable timestamp), convert to seconds
    if (timeValue > 1e10) {
      return Math.floor(timeValue / 1000) as UTCTimestamp;
    }
    return timeValue as UTCTimestamp;
  }
  
  // For strings with time (YYYY-MM-DD HH:MM:SS), convert to UTC timestamp
  // We parse it as UTC to avoid timezone conversion - treating the string as if it's already UTC
  const dateStr = String(timeValue).trim();
  
  // Check if it's a datetime string with time component
  const datetimeMatch = dateStr.match(/^(\d{4})-(\d{2})-(\d{2})(?:\s+(\d{2}):(\d{2}):(\d{2}))?$/);
  
  if (datetimeMatch) {
    const [, year, month, day, hour = "00", minute = "00", second = "00"] = datetimeMatch;
    
    // Use Date.UTC to create timestamp treating the values as UTC (no timezone conversion)
    const timestamp = Date.UTC(
      parseInt(year),
      parseInt(month) - 1, // Month is 0-indexed
      parseInt(day),
      parseInt(hour),
      parseInt(minute),
      parseInt(second)
    );
    
    // Convert to seconds (UTCTimestamp expects seconds since epoch)
    return Math.floor(timestamp / 1000) as UTCTimestamp;
  }
  
  // If it's just a date (YYYY-MM-DD), return as string (lightweight-charts supports this)
  if (/^\d{4}-\d{2}-\d{2}$/.test(dateStr)) {
    return dateStr as Time;
  }
  
  // If it's a Unix timestamp string, convert to number
  const timestamp = parseInt(dateStr);
  if (!isNaN(timestamp)) {
    return (timestamp > 1e10 ? Math.floor(timestamp / 1000) : timestamp) as UTCTimestamp;
  }
  
  console.warn(`Could not parse time value: ${timeValue}`);
  return Math.floor(Date.now() / 1000) as UTCTimestamp;
};

// Helper to convert Time to number for sorting
// Preserves original time without timezone conversion - just for comparison
export const timeToNumber = (time: Time): number => {
  if (typeof time === "number") {
    return time;
  }
  if (typeof time === "string") {
    // For strings in format "YYYY-MM-DD HH:MM:SS" or "YYYY-MM-DD",
    // we can sort them directly as strings since the format is naturally sortable
    // But to ensure proper numeric sorting, we'll convert to a comparable number
    // by treating the string as literal digits without any timezone interpretation
    
    // Remove non-numeric characters and create a sortable number
    // "2025-12-04 10:30:00" becomes 20251204103000
    const numericString = time.replace(/[^\d]/g, '');
    const numeric = parseInt(numericString);
    
    // If parsing fails, return 0
    return isNaN(numeric) ? 0 : numeric;
  }
  // For BusinessDay objects, convert using the numeric values directly
  const day = (time as any).day || 1;
  const month = (time as any).month || 1;
  const year = (time as any).year || 1970;
  // Create numeric representation: YYYYMMDD
  return year * 10000 + month * 100 + day;
};

// Helper to get value with case-insensitive key matching
export const getValue = (obj: any, keys: string[]): any => {
  for (const key of keys) {
    if (key in obj && obj[key] != null) {
      return obj[key];
    }
  }
  return null;
};

