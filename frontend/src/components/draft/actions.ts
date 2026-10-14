// What the draft view can ask the rest of the studio to do. One object, made by
// the studio and handed down, so the draft components stay ignorant of where
// a note lives or how a dialog is opened.

import type { ArticleRef } from "../../api/types";

export interface ImageToAdd {
  draft: string;
  index: number;
  caption: string;
  previewUrl: string;
  mediaId: string | null;
}

export interface DraftActions {
  addText(text: string, draft: string): void;
  hasText(text: string): boolean;
  addImage(image: ImageToAdd): void;
  hasImage(draft: string, index: number): boolean;
  /** Open "Dig deeper" on a passage's plain text. */
  digDeeper(passage: string): void;
  /** Open "Steer this draft", with these source refs already marked distrusted. */
  steer(distrust?: string[]): void;
  linkTo(target: string): { href: string; ref: ArticleRef } | null;
}
