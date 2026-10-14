// Brief confirmations ("Saved into Tea") and failures, in one corner.

import { Toast } from "radix-ui";
import { createContext, useCallback, useContext, useState, type ReactNode } from "react";

export interface Notice {
  title: string;
  description?: string;
  tone?: "ok" | "danger";
  action?: { label: string; href: string };
}

type Notify = (notice: Notice) => void;

const ToastContext = createContext<Notify>(() => {});

export function useNotify(): Notify {
  return useContext(ToastContext);
}

export function Toaster({ children }: { children: ReactNode }) {
  const [notices, setNotices] = useState<(Notice & { id: number })[]>([]);
  const notify = useCallback<Notify>((notice) => {
    setNotices((all) => [...all.slice(-2), { ...notice, id: Date.now() + Math.random() }]);
  }, []);
  const drop = (id: number) => setNotices((all) => all.filter((n) => n.id !== id));

  return (
    <ToastContext.Provider value={notify}>
      <Toast.Provider swipeDirection="right" duration={5000}>
        {children}
        {notices.map((notice) => (
          <Toast.Root
            key={notice.id}
            className={`st-toast st-toast-${notice.tone ?? "ok"}`}
            onOpenChange={(open) => !open && drop(notice.id)}
          >
            <Toast.Title className="st-toast-title">{notice.title}</Toast.Title>
            {notice.description ? (
              <Toast.Description className="st-toast-desc">
                {notice.description}
              </Toast.Description>
            ) : null}
            {notice.action ? (
              <Toast.Action asChild altText={notice.action.label}>
                <a className="st-toast-action" href={notice.action.href}>
                  {notice.action.label}
                </a>
              </Toast.Action>
            ) : null}
          </Toast.Root>
        ))}
        <Toast.Viewport className="st-toast-viewport" />
      </Toast.Provider>
    </ToastContext.Provider>
  );
}
