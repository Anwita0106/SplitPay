Reserved for shared custom React hooks. None were needed yet — every page
in this build uses plain `useState`/`useEffect` directly, which was
clearer for a project this size. Add hooks here if logic starts repeating
across pages (e.g. a `useGroupBalances` hook if more pages need it).
