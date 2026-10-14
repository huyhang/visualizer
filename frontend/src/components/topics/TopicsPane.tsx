import type { AskRequest, Availability, NoteSummary } from "../../api/types";
import { countTopics, type TopicNode } from "../../logic/topics";
import { EmptyState } from "../ui/EmptyState";
import { Skeleton } from "../ui/Skeleton";
import { AskBox } from "./AskBox";
import { BoxStatus } from "./BoxStatus";
import { NotesList } from "./NotesList";
import { TopicTree } from "./TopicTree";

export interface TopicsPaneProps {
  availability: Availability | undefined;
  topics: TopicNode[] | undefined;
  topicsError: string | null;
  notes: NoteSummary[] | undefined;
  selectedId: string | null;
  activeNote: string | null;
  asking: boolean;
  askError: string | null;
  onAsk: (request: AskRequest) => Promise<unknown>;
  onSelect: (id: string) => void;
  onOpenNote: (slug: string) => void;
}

export function TopicsPane(props: TopicsPaneProps) {
  const { availability, topics } = props;
  const canSubmit = !!availability?.can_submit;
  const unavailable = availability && !canSubmit ? availability.message : null;

  return (
    <section className="st-pane st-topics" aria-label="Topics">
      <div className="st-topics-head">
        <BoxStatus availability={availability} />
        <AskBox
          canSubmit={canSubmit}
          unavailable={unavailable}
          busy={props.asking}
          error={props.askError}
          onAsk={props.onAsk}
        />
      </div>
      <div className="st-scroll">
        <h2 className="st-section-title">
          Topics{" "}
          {topics?.length ? <span className="st-count">{countTopics(topics)}</span> : null}
        </h2>
        {props.topicsError ? (
          <p className="st-error-text st-pad" role="alert">
            {props.topicsError}
          </p>
        ) : !topics ? (
          <div className="st-pad">
            <Skeleton lines={4} />
          </div>
        ) : topics.length ? (
          <TopicTree
            nodes={topics}
            selectedId={props.selectedId}
            onSelect={props.onSelect}
          />
        ) : (
          <EmptyState icon="sparkle" title="Nothing researched yet">
            Ask a question above. The researcher reads the web and writes you a cited draft.
          </EmptyState>
        )}
        <h2 className="st-section-title">
          Notes{" "}
          {props.notes?.length ? (
            <span className="st-count">{props.notes.length}</span>
          ) : null}
        </h2>
        {props.notes ? (
          <NotesList
            notes={props.notes}
            activeSlug={props.activeNote}
            onOpen={props.onOpenNote}
          />
        ) : (
          <div className="st-pad">
            <Skeleton lines={2} />
          </div>
        )}
      </div>
    </section>
  );
}
