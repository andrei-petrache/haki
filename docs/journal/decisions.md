# Decisions and lessons

The rule that keeps coming back: pick the option that protects the data and
can be verified, even when it is slower.

## Decisions

| Decision | Why |
| --- | --- |
| Wait for ArgoCD v3.6.0 final + 7 days, not v3.5.6 | v3.5.6 is not tested on Kubernetes 1.37; a new cluster on 1.36 would delete the data |
| Migration hook in the Sync phase, not PreSync | ConfigMaps carry a hash in their name; a PreSync hook would start before the new ConfigMap exists |
| Prod stays on the manual phases during S8 | Learn ArgoCD on staging first; promotion to prod with approval comes in S9 |
| Envoy Gateway instead of ingress-nginx | ingress-nginx was retired; Gateway API is its maintained successor |
| Build each image once | What was tested is exactly what ships; no rebuild in later jobs |
| Tags are commit SHAs, never `latest` | Always know which version runs in each environment |
| Staging first, then prod | A new tag is tried on staging before it reaches the real data |
| "Load more" pagination in the first Workouts UI | Without it, workout 21 would silently hide the oldest one |
| Browser checks with Playwright, not by hand | Catches cases that are hard to reproduce by hand: double clicks, 409s, the ro-RO locale |
| A separate test account, deleted at the end with SQL | My development data stays clean |
| Leave the minimatch alert open | It is only in dev tools; `npm audit fix --force` would break ESLint |
| Never `docker compose down -v` | It deletes the `db-data` volume with my data |

## Bugs caught before they shipped

| Found | What it would have done | Lesson |
| --- | --- | --- |
| Login and signup had no limit, 64 MiB per Argon2 hash (H1) | Exhaust the pod's memory | Expensive operations need a limit: rate limit in Nginx, bounded concurrent hashing |
| Any JWT secret was accepted, even the placeholder (H2) | Forgeable tokens | Refuse a bad configuration at startup |
| Ids above 2,147,483,647 returned 500 (M1) | A server error instead of 404 | Validate input against the database's limits |
| A `%` in the database password broke migrations (M2) | A failed deploy | Build the database URL from separate fields, never as text |
| `Number('')` is 0 | An empty weight became "bodyweight" | Empty is an error; 0 is written explicitly |
| `NaN` passes both `< 0` and `> 1000` | "abc" would have been valid | Check `Number.isFinite` first, then the range |
| `new Date('2026-11-02')` is read as UTC | The previous day shown west of Greenwich | Split the date into year, month and day |
| Commits landed on local `main` instead of the branch | Work on the wrong branch | Run `git branch --show-current` in the same command as the commit |
| Nginx crash-looped on a cold cluster start | Frontend down until the backend existed | Resolve the backend per request: `resolver` + a variable in `proxy_pass` |
| A forged X-Forwarded-For bypassed the rate limit | A fresh login budget per header value | Trust the header only from a known proxy (Envoy) |
| The editor did not validate the date range | A 422 from the API without saying which field | Mirror the backend's rules in the form, with the error next to the field |
| `pg_isready` on the socket passed on PostgreSQL's temporary init server (L18) | `migrate` and `backend` starting just before the database restarts | Check readiness the way clients connect: over TCP |
| A database outage gave 502 from Nginx in Kubernetes (L19) | Clients saw a broken gateway instead of "try again in 5 s" | When the proxy answers for the backend, answer what the backend would |
| My own review suggested PreSync for migrations | The migration would look for a ConfigMap that does not exist yet | Check the official documentation, even for what you wrote yourself |
