// A scene's row of actions. Reading is for everyone; editing for those who
// may write; deleting shows, disabled and saying why, to an editor who does
// not own the book -- visibly unavailable rather than silently absent.

import { IconButton } from "../../../components/ui/Button";

export interface SceneActions {
  open: (id: string) => void;
  edit?: (id: string) => void;
  /** Absent when the reader may not delete; `canDelete` says whether to show it disabled. */
  remove?: (id: string) => void;
  canWrite: boolean;
  canDelete: boolean;
}

export function SceneTools({
  scene,
  actions,
}: {
  scene: { id: string; title: string };
  actions: SceneActions;
}) {
  return (
    <div className="cw-scene-tools">
      <IconButton
        icon="panel"
        label={`Open “${scene.title}” beside the list`}
        onClick={() => actions.open(scene.id)}
      />
      {actions.canWrite && actions.edit ? (
        <IconButton
          icon="edit"
          label={`Edit “${scene.title}”`}
          onClick={() => actions.edit?.(scene.id)}
        />
      ) : null}
      {actions.canWrite ? (
        actions.canDelete && actions.remove ? (
          <IconButton
            icon="trash"
            label={`Delete “${scene.title}”`}
            onClick={() => actions.remove?.(scene.id)}
          />
        ) : (
          <IconButton
            icon="trash"
            label="Only the book's owner may delete a scene"
            disabled
          />
        )
      ) : null}
    </div>
  );
}
