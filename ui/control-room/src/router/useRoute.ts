import { useEffect, useState } from "react";
import { type MatchedRoute, type Route, matchRoute, routeHref } from "./routes";

const NAVIGATE_EVENT = "control-room:navigate";

export const navigate = (route: Route): void => {
  window.history.pushState(null, "", routeHref(route));
  window.dispatchEvent(new Event(NAVIGATE_EVENT));
};

export const useRoute = (): MatchedRoute => {
  const [route, setRoute] = useState<MatchedRoute>(() => matchRoute(window.location.pathname));
  useEffect(() => {
    const sync = () => setRoute(matchRoute(window.location.pathname));
    window.addEventListener("popstate", sync);
    window.addEventListener(NAVIGATE_EVENT, sync);
    return () => {
      window.removeEventListener("popstate", sync);
      window.removeEventListener(NAVIGATE_EVENT, sync);
    };
  }, []);
  return route;
};
