/* jobhunt — single-page local app: ES modules, no build step, no external dependencies. */
import { route } from "./router.js";
import { pollApply, pollTask, refreshClaudePill } from "./topbar.js";

window.addEventListener("hashchange", route);
route();
refreshClaudePill();
pollTask();
pollApply();
