export class ApiError extends Error {
  status: number;
  details: unknown;

  constructor(message: string, status: number, details: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.details = details;
  }
}

interface FetchJsonOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
  timeoutMs?: number;
}

export async function fetchJson<T>(
  url: string,
  options: FetchJsonOptions = {}
): Promise<T> {
  const { method = "GET", body, timeoutMs = 20000 } = options;

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetch(url, {
      method,
      headers: {
        "Content-Type": "application/json",
      },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: controller.signal,
    });

    const text = await response.text();
    const parsed = text ? safeParseJson(text) : null;

    if (!response.ok) {
      throw new ApiError(
        typeof parsed === "object" && parsed && "detail" in parsed
          ? String((parsed as { detail?: unknown }).detail)
          : `Request failed with status ${response.status}`,
        response.status,
        parsed
      );
    }

    return parsed as T;
  } catch (error) {
    if (error instanceof ApiError) {
      throw error;
    }

    if (error instanceof Error && error.name === "AbortError") {
      const seconds = Math.max(1, Math.round(timeoutMs / 1000));
      const host = extractHost(url);
      const hostText = host ? ` (${host})` : "";

      throw new ApiError(
        `Request timed out after ${seconds}s${hostText}. Check API URL and backend reachability. If using a physical phone, use your computer LAN IP instead of localhost.`,
        408,
        { url, timeoutMs }
      );
    }

    throw new ApiError(
      error instanceof Error ? error.message : "Network error",
      0,
      null
    );
  } finally {
    clearTimeout(timeout);
  }
}

function safeParseJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

function extractHost(url: string): string | null {
  try {
    return new URL(url).host;
  } catch {
    return null;
  }
}
