// The ask box's settings, and the request they make.

import type { AskRequest } from "../api/types";

export interface AskOptions {
  languages: string;
  maxSources: number;
  includeImages: boolean;
  reviewPlan: boolean;
  verify: "auto" | "required" | "off";
}

export const DEFAULT_OPTIONS: AskOptions = {
  languages: "en",
  maxSources: 8,
  includeImages: true,
  reviewPlan: false,
  verify: "auto",
};

const LANGUAGE = /^[a-z]{2}(-[A-Z]{2})?$/;

/** "en, zh-TW" -> ["en", "zh-TW"], or the reason it will not do. */
export function parseLanguages(text: string): string[] | string {
  const codes = [...new Set(text.split(/[\s,]+/).filter(Boolean))];
  if (!codes.length) return "Name at least one language, such as en.";
  if (codes.length > 5) return "At most five languages.";
  const bad = codes.find((code) => !LANGUAGE.test(code));
  return bad ? `"${bad}" is not a language code like en or zh-TW.` : codes;
}

export const MIN_QUESTION = 3;
export const MAX_QUESTION = 500;

/** Why this question cannot be asked yet, or null when it can. */
export function questionProblem(question: string): string | null {
  const length = question.trim().length;
  if (length < MIN_QUESTION) return "Ask a question of at least three characters.";
  if (length > MAX_QUESTION) return `Keep the question under ${MAX_QUESTION} characters.`;
  return null;
}

export function askRequest(
  question: string,
  options: AskOptions,
  parent: string | null = null,
): AskRequest {
  const languages = parseLanguages(options.languages);
  return {
    question: question.trim(),
    languages: Array.isArray(languages) ? languages : ["en"],
    max_sources: Math.max(1, Math.min(15, Math.round(options.maxSources))),
    include_images: options.includeImages,
    approve_plan: options.reviewPlan,
    verify: options.verify,
    ...(parent ? { parent } : {}),
  };
}
