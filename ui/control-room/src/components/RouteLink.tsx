import type { AnchorHTMLAttributes, MouseEvent, ReactNode } from "react";
import { type Route, routeHref } from "@/router/routes";
import { navigate } from "@/router/useRoute";

type Props = Omit<AnchorHTMLAttributes<HTMLAnchorElement>, "href" | "onClick"> & { to: Route; children: ReactNode };

const isPlainLeftClick = (e: MouseEvent) => e.button === 0 && !e.metaKey && !e.ctrlKey && !e.shiftKey && !e.altKey;

export default function RouteLink({ to, children, ...rest }: Props) {
  const onClick = (e: MouseEvent<HTMLAnchorElement>) => {
    if (!isPlainLeftClick(e)) return;
    e.preventDefault();
    navigate(to);
  };
  return (
    <a href={routeHref(to)} onClick={onClick} {...rest}>
      {children}
    </a>
  );
}
