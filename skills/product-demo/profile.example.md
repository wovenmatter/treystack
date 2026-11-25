# Demo profile

<!--
Copy this file to demo-profile.md in the folder you run your agent from (or a parent
folder), or name its path in your CLAUDE.md / AGENTS.md, e.g.
  Demo profile: ~/notes/demo-profile.md
The product-demo skill reads it at the start of every run. Delete what you do not need;
anything missing falls back to the skill's neutral defaults.
The products below are fictional placeholders. Replace them with yours.
-->

## Defaults

- Destination: X (other options: LinkedIn, landing page, blog)
- Length: 20-30 s (sometimes 60-90 s for a walkthrough)
- Shape: 16:9, 1920x1080, 30 fps
- Look: polished            <!-- polished | plain -->
- Audio: silent             <!-- silent | music | narration | dub -->
- Captions: yes when there is voice
- Music: fetch from Mixkit, mood "positive"   <!-- or a path to your own file -->
- Who records: me           <!-- me (mode A) | agent (mode B) -->
- Dub offset: 0 ms          <!-- from the one-time clap test, e.g. +80 ms for a wireless mic -->

## Where demos go

- Demo folders: ~/Movies/demos   <!-- one <YYYY-MM-DD>-<slug> folder per demo -->

## Products

### Acme Notes (macOS app)
- Window title contains: "Acme Notes"
- Launch: open -a "Acme Notes"
- Window size: 1280x720
- Safe data: File > Open Sample Library (fake notes, fake names)
- Never show: the Accounts sidebar, any real customer name, the Billing tab, email addresses

### Example Web Dashboard (website)
- Window title contains: "Example Dashboard"
- Launch: open the staging URL in a separate browser profile with no bookmarks bar
- Safe data: log in as the demo user (seeded test data)
- Never show: the browser address bar, API keys on Settings > Developer

## Notes

- Brand background for the polished look: #0f172a
- Always end on the export screen
