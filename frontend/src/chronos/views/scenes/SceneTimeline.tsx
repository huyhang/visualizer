// The book's clock as a scrollable rail: scroll and the cursor moves through
// time, the few scenes nearest it hang either side, the calendar's turnings
// mark the ground, and empty stretches fold into breaks. The geometry is all
// in logic/scenes/timelineLayout.ts; this owns scrolling, measuring and the
// cursor's reading. Cards are drawn by the caller (`renderCard`), so the rail
// knows nothing about scenes beyond their two ticks.

import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type KeyboardEvent,
  type ReactNode,
} from "react";
import type { TimelineEvent } from "../../api/types";
import { tickLabels } from "../../logic/scenes/cursorLabel";
import {
  ZOOMS,
  densityBins,
  displayPlacements,
  periodBands,
  railGeometry,
  ratioForTick,
  scaleFor,
  scrollForTick,
  seedLabels,
  stepZoom,
  storyOrder,
  tickAtRatio,
  tickAtScroll,
  visibleBreaks,
  visiblePeriods,
  visibleScenes,
  type Bounds,
  type RailScene,
} from "../../logic/scenes/timelineLayout";
import { plural } from "../../logic/text";
import { Button } from "../../../components/ui/Button";

export type Scheduled = TimelineEvent & RailScene;

/** The scheduled scenes as the rail reads them: both ticks known. */
export function railScenes(events: TimelineEvent[]): Scheduled[] {
  return events.filter(
    (e): e is Scheduled =>
      e.scheduled && typeof e.start_tick === "number" && typeof e.end_tick === "number",
  );
}

const NARROW = 720;
// How long the cursor must hold still before a screen reader is told where it is.
const ANNOUNCE_DELAY = 120;

interface Props {
  events: Scheduled[];
  bounds: Bounds;
  initialTick: number | null;
  initialZoom: number;
  onCursor: (tick: number) => void;
  onZoom: (zoom: number) => void;
  formatTick: (tick: number) => Promise<string | null | undefined>;
  renderCard: (scene: Scheduled) => ReactNode;
  tintOf: (scene: Scheduled) => string | null;
}

const clampTick = (bounds: Bounds, tick: number) =>
  Math.min(bounds.end_tick, Math.max(bounds.start_tick, Number(tick)));

/** The stage's size, kept current as the window or the inspector changes it. */
function useStageSize(ref: React.RefObject<HTMLDivElement | null>) {
  const [size, setSize] = useState({ width: 900, height: 560 });
  useLayoutEffect(() => {
    const node = ref.current;
    if (!node) return;
    const measure = () =>
      setSize({ width: node.clientWidth || 900, height: node.clientHeight || 560 });
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(node);
    return () => observer.disconnect();
  }, [ref]);
  return size;
}

/** The cursor's reading: a date, never flipping to a bare tick once one is known. */
function useCursorReading(
  events: Scheduled[],
  tick: number,
  formatTick: Props["formatTick"],
) {
  const [label, setLabel] = useState("");
  const [announced, setAnnounced] = useState("");
  const reading = useRef<ReturnType<typeof tickLabels> | null>(null);
  useEffect(() => {
    const labels = tickLabels({
      formatTick,
      seeded: seedLabels(events),
      onLabel: setLabel,
    });
    reading.current = labels;
    return () => labels.stop();
  }, [events, formatTick]);
  useEffect(() => reading.current?.cursorAt(tick), [tick, events, formatTick]);
  // A live region rewritten every frame is a queue nobody can listen through; only the settled reading is said.
  useEffect(() => {
    const timer = setTimeout(() => setAnnounced(label), ANNOUNCE_DELAY);
    return () => clearTimeout(timer);
  }, [label]);
  return { label, announced };
}

function RailItem({
  placement,
  columns,
  tint,
  children,
}: {
  placement: { top: number; anchorY: number; endY: number; opacity: number; side: number };
  columns: number;
  tint: string | null;
  children: ReactNode;
}) {
  const g = railGeometry(placement);
  const style = {
    top: placement.top,
    opacity: placement.opacity,
    "--anchor-y": `${g.anchor}px`,
    "--duration-top": `${g.durationTop}px`,
    "--duration-height": `${g.durationHeight}px`,
    "--stem-top": `${g.stemTop}px`,
    "--stem-height": `${g.stemHeight}px`,
    ...(tint ? { "--thread": tint } : {}),
  } as CSSProperties;
  return (
    <div className={`cw-tl-item side-${columns === 1 ? 1 : placement.side}`} style={style}>
      {["duration", "stem", "link", "dot"].map((part) => (
        <span key={part} className={`cw-tl-${part}`} aria-hidden="true" />
      ))}
      <div className="cw-tl-card">{children}</div>
    </div>
  );
}

/** Several scenes at one tick on a one-column stage: a moment that opens to list them. */
function Moment({
  scenes,
  renderCard,
}: {
  scenes: Scheduled[];
  renderCard: Props["renderCard"];
}) {
  const first = scenes[0]!;
  const names =
    scenes
      .slice(0, 3)
      .map((s) => s.title)
      .join(" · ") + (scenes.length > 3 ? ` · +${scenes.length - 3}` : "");
  return (
    <details className="cw-tl-moment">
      <summary>
        <span className="cw-tl-moment-count">
          {scenes.length} scenes at {first.start_label || `tick ${first.start_tick}`}
        </span>
        <span className="cw-tl-moment-names">{names}</span>
      </summary>
      <div className="cw-tl-moment-scenes">
        {scenes.map((s) => (
          <div key={s.id}>{renderCard(s)}</div>
        ))}
      </div>
    </details>
  );
}

function Overview({
  events,
  scale,
  tick,
  onMove,
}: {
  events: Scheduled[];
  scale: ReturnType<typeof scaleFor>;
  tick: number;
  onMove: (ratio: number) => void;
}) {
  const bins = useMemo(() => densityBins(events, scale), [events, scale]);
  const peak = Math.max(1, ...bins);
  return (
    <div className="cw-tl-overview">
      <div className="cw-tl-density" aria-hidden="true">
        {bins.map((amount, index) =>
          amount ? (
            <span
              key={index}
              style={{
                top: `${(index / bins.length) * 100}%`,
                opacity: 0.2 + (0.8 * amount) / peak,
              }}
            />
          ) : null,
        )}
      </div>
      <input
        className="cw-tl-range"
        type="range"
        min={0}
        max={1000}
        step={1}
        aria-label="Jump to a time on the story overview"
        value={Math.round(ratioForTick(scale, tick) * 1000)}
        onChange={(e) => onMove(Number(e.target.value) / 1000)}
      />
    </div>
  );
}

/** A wheel over a card or the rail moves the clock; the page around it stays put. */
function useWheelForwarding(
  stageRef: React.RefObject<HTMLDivElement | null>,
  scrollerRef: React.RefObject<HTMLDivElement | null>,
) {
  useEffect(() => {
    const stage = stageRef.current;
    if (!stage) return;
    const forward = (e: WheelEvent) => {
      const scroller = scrollerRef.current;
      const target = e.target as Element | null;
      if (!scroller || scroller.contains(target) || target?.closest(".cw-tl-moment-scenes"))
        return;
      e.preventDefault();
      scroller.scrollBy?.({ top: e.deltaY, behavior: "auto" });
    };
    stage.addEventListener("wheel", forward, { passive: false });
    return () => stage.removeEventListener("wheel", forward);
  }, [stageRef, scrollerRef]);
}

function TimelineTools({
  count,
  zoom,
  onZoom,
  onBeginning,
  onEnd,
}: {
  count: number;
  zoom: number;
  onZoom: (direction: number) => void;
  onBeginning: () => void;
  onEnd: () => void;
}) {
  return (
    <div className="cw-tl-tools">
      <span className="cw-muted cw-small cw-tl-count">
        {plural(count, "scheduled scene")}
      </span>
      <div className="cw-tl-zoom" role="group" aria-label="Zoom">
        <Button
          size="sm"
          variant="ghost"
          aria-label="Zoom timeline out"
          title="Show more time"
          disabled={zoom === ZOOMS[0]}
          onClick={() => onZoom(-1)}
        >
          −
        </Button>
        <span className="cw-tl-zoom-label">{Math.round(zoom * 100)}%</span>
        <Button
          size="sm"
          variant="ghost"
          aria-label="Zoom timeline in"
          title="Show less time"
          disabled={zoom === ZOOMS[ZOOMS.length - 1]}
          onClick={() => onZoom(1)}
        >
          +
        </Button>
      </div>
      <Button size="sm" onClick={onBeginning}>
        Beginning
      </Button>
      <Button size="sm" onClick={onEnd}>
        End
      </Button>
    </div>
  );
}

function PeriodLayer({ periods }: { periods: ReturnType<typeof visiblePeriods> }) {
  return (
    <div className="cw-tl-periods" aria-hidden="true">
      {periods.map((band) => (
        <div
          key={band.tick}
          className={`cw-tl-period level-${Math.min(1, band.level)} mark-${band.side}`}
          style={{ top: band.y }}
        >
          <span className="cw-tl-period-rule" />
          <span className="cw-tl-period-label">{band.labels.join(" · ")}</span>
        </div>
      ))}
    </div>
  );
}

function BreakLayer({ breaks }: { breaks: ReturnType<typeof visibleBreaks> }) {
  return (
    <div className="cw-tl-breaks" aria-hidden="true">
      {breaks.map((gap) => (
        <div key={gap.startTick} className="cw-tl-break" style={{ top: gap.y }}>
          <span className="cw-tl-break-line" />
          <span className="cw-tl-break-label">{gap.rawDuration} ticks later</span>
          <span className="cw-tl-break-line" />
        </div>
      ))}
    </div>
  );
}

export function SceneTimeline({
  events,
  bounds,
  initialTick,
  initialZoom,
  onCursor,
  onZoom,
  formatTick,
  renderCard,
  tintOf,
}: Props) {
  const stageRef = useRef<HTMLDivElement>(null);
  const scrollerRef = useRef<HTMLDivElement>(null);
  const size = useStageSize(stageRef);
  const columns = size.width < NARROW ? 1 : 2;
  const [zoom, setZoom] = useState(initialZoom);
  const [tick, setTick] = useState(() =>
    clampTick(bounds, initialTick ?? bounds.start_tick),
  );
  // The tick a rescale must keep in place, read inside the layout effect without re-running it.
  const tickRef = useRef(tick);
  useEffect(() => {
    tickRef.current = tick;
  }, [tick]);

  // Sorted once: `visibleScenes` runs on every frame, and the sort is what grows with the book.
  const order = useMemo(() => storyOrder(events), [events]);
  const bands = useMemo(() => periodBands(order.ordered), [order]);
  const scale = useMemo(
    () =>
      scaleFor(bounds, {
        viewportHeight: size.height,
        eventCount: events.length,
        events,
        zoom,
      }),
    [bounds, size.height, events, zoom],
  );
  const { label, announced } = useCursorReading(events, tick, formatTick);

  // A new scale puts the cursor's tick back where it was. `behavior: auto`, or
  // the stylesheet's smooth scrolling would read the old offset mid-animation.
  useLayoutEffect(() => {
    scrollerRef.current?.scrollTo?.({
      top: scrollForTick(scale, tickRef.current),
      behavior: "auto",
    });
  }, [scale]);

  const frameRef = useRef<number | null>(null);
  const onScroll = useCallback(() => {
    if (frameRef.current !== null) return;
    frameRef.current = requestAnimationFrame(() => {
      frameRef.current = null;
      const next = tickAtScroll(scale, scrollerRef.current?.scrollTop ?? 0);
      setTick(next);
      onCursor(next);
    });
  }, [scale, onCursor]);
  useEffect(
    () => () => {
      if (frameRef.current !== null) cancelAnimationFrame(frameRef.current);
    },
    [],
  );

  const moveTo = useCallback(
    (target: number, smooth: boolean) => {
      const next = clampTick(bounds, target);
      scrollerRef.current?.scrollTo?.({
        top: scrollForTick(scale, next),
        behavior: smooth ? "smooth" : "auto",
      });
      setTick(next);
      onCursor(next);
    },
    [bounds, scale, onCursor],
  );

  useWheelForwarding(stageRef, scrollerRef);

  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    const page = Math.max(80, scale.viewportHeight * 0.72);
    const steps: Record<string, number> = {
      ArrowUp: -48,
      ArrowDown: 48,
      PageUp: -page,
      PageDown: page,
    };
    if (e.key === "Home") moveTo(bounds.start_tick, false);
    else if (e.key === "End") moveTo(bounds.end_tick, false);
    else if (steps[e.key] !== undefined)
      scrollerRef.current?.scrollBy?.({ top: steps[e.key] });
    else return;
    e.preventDefault();
  };

  const changeZoom = (direction: number) => {
    const next = stepZoom(zoom, direction);
    if (next === zoom) return;
    setZoom(next);
    onZoom(next);
  };

  // The cards decide where the rule goes, so they are laid out first and the
  // other layers measure from what they settled on.
  const { cards, cursorY, scrim } = visibleScenes(order, scale, tick, {
    viewportHeight: scale.viewportHeight,
    columns,
  });
  const breaks = visibleBreaks(scale, tick, { cursorY });
  const periods = visiblePeriods(bands, scale, tick, { cursorY });
  const stageStyle = {
    "--cursor-y": `${cursorY}px`,
    "--fade-top": scrim.top,
    "--fade-bottom": scrim.bottom,
  } as CSSProperties;

  return (
    <div className="cw-tl">
      <TimelineTools
        count={events.length}
        zoom={scale.zoom}
        onZoom={changeZoom}
        onBeginning={() => moveTo(bounds.start_tick, true)}
        onEnd={() => moveTo(bounds.end_tick, true)}
      />
      <div
        ref={stageRef}
        className={`cw-tl-stage${columns === 1 ? " is-narrow" : ""}`}
        style={stageStyle}
      >
        <div
          ref={scrollerRef}
          className="cw-tl-scroll"
          tabIndex={0}
          role="region"
          aria-label="Scene timeline. Scroll to move through time."
          onScroll={onScroll}
          onKeyDown={onKeyDown}
        >
          <div className="cw-tl-spacer" style={{ height: scale.contentHeight }} />
        </div>
        <PeriodLayer periods={periods} />
        <BreakLayer breaks={breaks} />
        <div className="cw-tl-layer">
          {displayPlacements(cards, columns).map((item) => (
            <RailItem
              key={item.key}
              placement={item.placement}
              columns={columns}
              tint={item.scenes.length > 1 ? null : tintOf(item.scenes[0]!)}
            >
              {item.scenes.length > 1 ? (
                <Moment scenes={item.scenes} renderCard={renderCard} />
              ) : (
                renderCard(item.scenes[0]!)
              )}
            </RailItem>
          ))}
        </div>
        <div className="cw-tl-cursor">
          <span className="cw-tl-rule" />
          <span className="cw-tl-label">{label}</span>
        </div>
        <span className="cw-tl-fade top" aria-hidden="true" />
        <span className="cw-tl-fade bottom" aria-hidden="true" />
        <Overview
          events={events}
          scale={scale}
          tick={tick}
          onMove={(ratio) => moveTo(tickAtRatio(scale, ratio), false)}
        />
      </div>
      <span className="st-sr-only" aria-live="polite">
        {announced}
      </span>
    </div>
  );
}
