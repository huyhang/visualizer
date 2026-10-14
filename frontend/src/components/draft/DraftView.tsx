import { Tabs } from "radix-ui";
import { useMemo } from "react";
import type { Draft } from "../../api/types";
import { quotesFrom, sourceNumbers } from "../../logic/citations";
import { slugOf } from "../../logic/format";
import type { TopicNode } from "../../logic/topics";
import { Badge } from "../ui/Badge";
import { Button } from "../ui/Button";
import type { DraftActions } from "./actions";
import { ArticleView } from "./ArticleView";
import { CitationContext, type CitationInfo } from "./CitationContext";
import { DraftDecisions, type DraftDecisionHandlers } from "./DraftDecisions";
import { FactsView } from "./FactsView";
import { ImagesView } from "./ImagesView";
import { SourcesView } from "./SourcesView";
import { SteeringPanel, type SteerPlanHandlers } from "./StatusCards";
import { TopicHeader } from "./TopicHeader";
import { VerificationBadge } from "./VerificationBadge";

/** A draft ready to read: the article, its facts, its sources, its pictures. */
export function DraftView({
  topic,
  path,
  draft,
  actions,
  previewUrl,
  decisions,
  steerPlan,
  onSelect,
}: {
  topic: TopicNode;
  path: TopicNode[];
  draft: Draft;
  actions: DraftActions;
  previewUrl: (index: number) => string;
  decisions: DraftDecisionHandlers;
  steerPlan: SteerPlanHandlers;
  onSelect: (id: string) => void;
}) {
  const slug = slugOf(draft.draft);
  const document = draft.article.document;
  const title =
    typeof document.title === "string" && document.title ? document.title : topic.title;
  const body = typeof document.body === "string" ? document.body : "";
  // The topic's copy is the one polled while the steer runs; the draft's is a
  // snapshot from when it was last fetched.
  const steering = topic.refinement ?? draft.refining;

  const citations = useMemo<CitationInfo>(() => {
    const numbers = sourceNumbers(draft.sources);
    const rows = new Map(draft.sources.map((row) => [row.ref, row]));
    return {
      number: (ref) => numbers.get(ref) ?? null,
      source: (ref) => rows.get(ref) ?? null,
      quotes: (ref) => quotesFrom(ref, draft.facts),
      onDistrust: (ref) => actions.steer([ref]),
    };
  }, [draft, actions]);

  const meta = (
    <>
      <VerificationBadge report={draft.verification} />
      {typeof document.era === "string" ? <Badge>{document.era}</Badge> : null}
      {typeof document.topic === "string" ? <Badge>{document.topic}</Badge> : null}
    </>
  );

  return (
    <CitationContext.Provider value={citations}>
      <TopicHeader
        topic={topic}
        path={path}
        title={title}
        onSelect={onSelect}
        badges={meta}
        actions={
          <>
            <Button
              size="sm"
              icon="steer"
              onClick={() => actions.steer()}
              disabled={!!steering && steering.state !== "failed"}
            >
              Steer
            </Button>
            <DraftDecisions inNotes={topic.job.notes.length > 0} handlers={decisions} />
          </>
        }
      />
      {steering ? <SteeringPanel job={steering} plan={steerPlan} /> : null}
      <Tabs.Root className="st-draft-tabs" defaultValue="article">
        <Tabs.List className="st-tabs" aria-label="Draft">
          <Tabs.Trigger className="st-tab" value="article">
            Article
          </Tabs.Trigger>
          <Tabs.Trigger className="st-tab" value="facts">
            Facts <span className="st-count">{draft.facts.length}</span>
          </Tabs.Trigger>
          <Tabs.Trigger className="st-tab" value="sources">
            Sources <span className="st-count">{draft.sources.length}</span>
          </Tabs.Trigger>
          {draft.images.length ? (
            <Tabs.Trigger className="st-tab" value="images">
              Images <span className="st-count">{draft.images.length}</span>
            </Tabs.Trigger>
          ) : null}
        </Tabs.List>
        <Tabs.Content className="st-tab-panel" value="article">
          <ArticleView body={body} draft={slug} actions={actions} />
        </Tabs.Content>
        <Tabs.Content className="st-tab-panel" value="facts">
          <FactsView
            facts={draft.facts}
            dropped={draft.dropped_facts}
            draft={slug}
            actions={actions}
          />
        </Tabs.Content>
        <Tabs.Content className="st-tab-panel" value="sources">
          <SourcesView sources={draft.sources} facts={draft.facts} actions={actions} />
        </Tabs.Content>
        <Tabs.Content className="st-tab-panel" value="images">
          <ImagesView
            images={draft.images}
            draft={slug}
            previewUrl={previewUrl}
            actions={actions}
          />
        </Tabs.Content>
      </Tabs.Root>
    </CitationContext.Provider>
  );
}
