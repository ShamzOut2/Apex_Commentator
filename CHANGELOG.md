# Changelog

What's changed in each version, in plain words. The newest version's notes
show in the app's update pop-up and in the README's "What's new".

How each version's entry is written:

- A `## vX.Y.Z` heading (`## Unreleased` until it's released).
- Up to three sections, in this order: `### New features`,
  `### Improvements` and `### Fixes`. Leave out any that are empty.
- One short line per change, saying what the commentator will notice, not
  how it was done. Details belong in the README.

## Unreleased

### New features

- **Driver on camera**: a small board at the bottom centre names the driver
  you're spectating (position, number, name, team and car). It slides in each
  time the camera moves to someone, and can hide itself after a few seconds.
- **Import and export** leagues (with all their images), teams,
  championships, round results, the driver roster and overlay settings.
  Exports go to `Documents\Apex Commentator\Exports`, and the app shows
  where each one went, with a button to open the folder. Standings, results
  and the roster also export as spreadsheets (CSV).

- **Size** for every overlay and board (50–200%). An overlay grows or
  shrinks from where it sits; a board from the middle of the screen.

### Improvements

- The Sponsors overlay's panel sits closer around the logos. In "one at a
  time" mode it fits whichever logo is showing.

### Fixes

- Scrolling with the mouse over a number box you'd clicked in (like a
  round's points multiplier) no longer changes its value by accident.
- "Show on my screen" overlays covered the whole monitor in dark instead of
  being see-through (since v0.4.4). They're see-through again, and the app
  checks with you after each update in case they ever come up solid.

## v0.4.4

### Fixes

- An overlay's or board's background now only colours the overlay or board
  itself (the tower, the lap trackers, the sponsors panel, the grid walk
  cards, the board), not the whole screen.
- Buttons and settings stopped responding once several tabs, pop-outs or
  on-screen overlays were open. That's why changing things during a session
  and after an update often didn't work. They now always respond.
- "Show on my screen", **Remove** and **Remove all from my screen** work
  reliably.

## v0.4.3

### New features

- **Show on my screen**: put any overlay or board straight on your monitor,
  over iRacing, instead of using OBS or a browser. Pick the monitor; your
  mouse and keyboard go straight through to the game.
- **Backgrounds** for every overlay and board: the default look, a solid
  colour or your own image, each with adjustable opacity.

### Improvements

- The standings tower starts each race with just the header (laps or time
  left). Each driver appears as they finish lap 1, and nobody shows before
  the green. This is now on by default.
- When a race goes green, the standings header flashes green five times
  with a light sweep, then stops.

## v0.4.2

### New features

- **Full-screen boards** with one-click buttons (Boards tab): championship
  standings (overall and each class), teams' and manufacturers'
  championships, the season calendar, and finishing orders.
- **Sponsor logos**: add them in the League builder, show them on any edge
  of a board, or over the race with the new Sponsors overlay.
- **League logo, banners and calendar image** in the League builder, for the
  boards.
- **Car makes**: manufacturer badges, and a Car field for each driver.
- **Season calendar** with iRacing's tracks and layouts to pick from.
- **Fastest lap** on the standings tower: a purple stopwatch by the holder,
  and a "NEW FASTEST LAP" pill at the top of the screen.
- **Close racing**: the interval turns red when a driver is within 0.15 s of
  the car ahead.
- **Last few drivers** can be added at the bottom of the Overall tower.
- **Contact between cars** is logged in the race log.
- **Pop out** the Timing and Boards tabs into their own windows.
- **"Remove driver class in name"** for leagues that tag names like
  `(P) Dave Price`, with classes picked up from the tags.
- **Standings tower options**: laps or time left in the header, choose your
  columns, and fill the tower in as drivers complete lap 1.
- **What's new** notes like these in the update pop-up and the README.

### Improvements

- Smooth transitions: boards fade between each other, and drivers slide
  up and down when they change places.
- Spins are only called spins when the car actually rotates; hard braking
  for a slow corner no longer counts.
- Class and overall championships say what each table is scored on, and
  teams count overall points (or class points, if you choose).
- Larger team logos on the teams' board.
- By-class standings have an even gap between the header and each class.

### Fixes

- Race gaps no longer stick or lag behind the running order. Lapped cars
  show "+1 L".

## v0.4.1

- **Lap tracker readable on real tracks**: iRacing often splits a lap into
  many short sections, and the sector times piled on top of each other.
  - Sectors are now merged into 3 by default, like a TV broadcast. The
    *Sectors* setting in the Overlays tab offers 2, 3, 4 or every split
    point.
  - Each sector is a pill that fills as the car goes round and turns solid
    with its time inside. A pill too narrow for its time shows only its
    colour.
  - Small trackers keep a readable width and wrap onto a second row rather
    than shrinking.
- `--mock-sectors N` gives the simulated track N split points.

## v0.4.0

- **Full-screen displays**: the standings and the qualifying lap tracker each
  have a full-screen version (`?screen=1`, linked from the Overlays tab).
  - Standings board: every driver, with laps, gaps, intervals, last and best
    laps, and pit stops.
  - Qualifying live timing: sector boxes, the running lap clock, best lap and
    gap.
- **Championship scoring "Both"**: each result scores in its class's
  championship (class positions) and in an Overall championship (overall
  positions), kept apart. The overall championship can have its own points
  table.
- **Finished / DNF / DNS fixed**: imported results no longer mark everyone as
  finished.
  - The app watches the race: a car finished if it took the chequered flag.
  - A car that started but didn't take the flag is a DNF.
  - A car that never joined once the race went green is a DNS.
- **Race distance to score**: a driver must complete a share of their class
  winner's laps (75% by default). Anyone short is a DNF with no points.
- Live championship standings no longer count a race twice once it has been
  imported.
- `--mock-laps N` ends the simulated race after N laps; simulated cars can
  retire.
- **Updates panel** on the Home page:
  - Shows your version, the newest version, when it last checked and any
    problem.
  - **Check now**, **Install update** and **Release page** buttons.
  - Update checks used to fail silently, and on a private repository they
    always failed ("not found"). The panel now says so, and takes a GitHub
    access token so private releases can be seen and installed.
  - The update pop-up now appears whenever a check finds a new version, not
    only when the app opens.
- **Photo booth "WinError 448: untrusted mount point" fixed**: when
  `Documents\iRacing` is a folder link (junction) to another drive, the app
  follows it to the real folder. A **Screenshots folder** setting under the
  photo booth lets you pick the folder by hand.

## v0.3.0

- **Championship** tab: season points for each league.
  - **Rules**: points for finishing positions and, if you want them,
    qualifying positions. Bonuses for pole, fastest lap (optionally top N
    only), leading a lap, each lap led, most laps led, most places gained, a
    clean race, finishing, starting and the win. Drop rounds, a minimum share
    of laps to be classified, and whether DNFs score.
  - **Championships**: one per class, or one overall, plus a team
    championship (optionally each team's best N drivers per round).
  - **Rounds**: double-points (or any multiplier) and can't-drop rounds.
    *Import from session* fills a round from the race you're in (laps, laps
    led, fastest laps, grid, incidents, DNFs). Every result can be corrected
    by hand, and extra points can be given or taken.
  - **Penalties**: points taken off after a race (never dropped) and licence
    penalty points, with reasons.
  - **Live standings** during a race: the championship as if the race
    finished now, with places and points gained, ready for a points-battle
    overlay.
- **Standings overlay** for stream (`/standings.html`): a timing tower,
  overall or by class, with team names, logos and colours. In qualifying it
  stays empty until drivers set clean laps.
- **Qualifying lap tracker** (`/laps.html`): a big tracker for the car on
  camera, plus small ones (you choose how many) for other cars on a timed lap.
  Sector bars turn purple, green or yellow against the driver's best or the
  class best. The lap time and its gap to the driver's best show for 5 s after
  the line. Name styles, car and driver numbers, and team names and logos are
  all optional.
- **Team builder** tab: teams with logos, short names and colours, and
  driver assignments. The roster gains a *Driver #* column.
- **Overlays** tab: OBS addresses, live previews and settings for the stream
  overlays.
- `--mock-session qualify` simulates a qualifying session.

- **Main page and navigation**: Home, Timing, Grid walk, League builder and
  Championship pages, with a Home page of tiles showing each one's status.
- **Timing screen** replaces the driver list and events tab. It has
  standings with class position, places gained/lost, gap, interval, flags and
  penalties. Battles within 0.15 s (adjustable) flash in a colour of your
  choice, and clicking a driver moves the camera to them. The race log lets
  you pick a line and replay it from 5–30 s before. There are camera buttons
  with configurable hotkeys, and a replay bar with rewind steps and LIVE.
- **Race log**: now logs pit in/out (stop time, places lost), places lost
  after an off, penalties (black flag, DQ, meatball, warning) and class
  fastest laps, alongside overtakes and incidents.
- **Logging fix**: logging no longer depends on iRacing reporting "live". It
  logs saved replays as they play, and pauses only while you rewind over
  something already logged. A status line shows whether it's running.
- **League builder**: *Add drivers from session* merges the session's
  drivers into a league without losing your edits.
- **Photo booth**: photographs every loaded car inside iRacing (camera on
  the car, iRacing's panels hidden, iRacing's own screenshot), cuts the car out
  of its background with an AI model, and saves it as the driver's car photo
  for the grid walk. It shows real liveries, Trading Paints included.

## v0.2.0

Apex Commentator is now a proper Windows program.

- **Windows installer**: download `ApexCommentator-Setup-0.2.0.exe` from the
  release and run it. No Python needed. It adds Start menu shortcuts (plus a
  *demo mode* one that runs a simulated race) and an optional desktop icon,
  and it can be uninstalled from Windows Settings.
- **Own window**: the control panel opens in its own app window instead of a
  browser tab. The grid walk page for OBS works as before.
- **Your data in one place**: settings, leagues, logos and photos live in
  `%APPDATA%\Apex Commentator`, so updates and reinstalls never touch them.
- **Updates**: the installed app updates itself from the release's installer.
  Click *Update now*, and it closes, updates and reopens.
- A portable zip of the app is attached to each release too.

## v0.1.0

First release of Apex Commentator.

- **Live driver list**: live race order, gaps, intervals, lap times, incident
  points, and pit and off-track status for every car in the session.
- **Spectate controls**: watch any driver, car ahead or behind, leader,
  iRacing's incident and exciting cameras, and camera groups.
- **Replays**: overtakes and incidents are detected for every car. One click
  replays a moment, by session time, then **Go live** takes you back.
- **League builder**: fetch a league roster by League ID, or build one from the
  session. Add nicknames, teams, notes, and classes with your own names,
  colours and logos, including the built-in PRO / SEMI-PRO / PRO-AM / AM /
  GOLD / SILVER / BRONZE tier logos.
- **Grid walk**: an on-stream graphic that walks the starting grid two
  drivers at a time on a timer. Styles: grid on track, grid map, or head to
  head. It shows livery, helmet, team and team logo, and qualifying gaps.
- **Updates**: the app checks GitHub for new releases on start-up and offers
  to install them in one click, keeping your settings and leagues.
