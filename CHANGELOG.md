# Changelog

Release notes for each version. When a version tag is pushed, its section
here becomes the GitHub release notes, which the app shows in its update
pop-up.

## Unreleased

- **Boards**: full-screen championship standings (overall and per class),
  teams' and manufacturers' championships, the season calendar, and
  finishing orders (latest round, any round, or live). They're put on screen
  with buttons in the new Boards tab, and each board's columns, league logo
  and banner are configurable. Standings can show the points gap to the
  leader and to the driver ahead. OBS page: `/board.html`.
- **Car makes**:
  - 37 manufacturer badges, from the Apex Overlays project; see
    THIRD_PARTY_NOTICES.md.
  - A roster *Car* field, worked out from the iRacing car or picked by hand.
  - Each result keeps its make, for the manufacturers' championship.
- **Season calendar**:
  - Rounds get a track and configuration chosen from lists, plus start time
    and length.
  - The track list is iRacing's official list when Data API credentials are
    set (*Fetch official track list*). Otherwise it's a built-in list plus
    the tracks seen in sessions.
- **League builder**: a league logo, horizontal and vertical banners, and the
  league's own calendar image for the boards.
- **Teams' championship board**: team colour stripe and logo, the drivers who
  scored, points per round, wins, penalties, and the gap to the leader and to
  the team ahead (all optional). The Boards tab always shows the Teams
  button and explains when there's nothing to show yet.
- **Class and overall championships ("both")**: each standings table says
  what it adds up (class positions or overall positions, with the points
  table). Teams now count their drivers' overall points by default; a new
  rule switches them to class points.

- **Standings header** shows laps or time left: "LAP 5 / 20", "FINAL LAP",
  "FINISHED" or "12:34 LEFT". Automatic follows how the session is limited,
  or you can choose.
- **Fill in as drivers complete a lap**: an option to start each session with
  only the header. Drivers appear as they cross the line, so the race tower
  builds up in order at the end of lap 1.
- **Standings columns to choose from**:
  - gap and interval;
  - places gained/lost;
  - best and last lap;
  - laps completed, pit stops and the PIT badge.
- The full-screen standings board shows laps or time left too, and counts
  laps completed.
- **By-class standings** have the same small gap between the header and each
  class, on the tower (each class its own panel) and the full-screen board.
- **League builder: "Remove driver class in name"** for leagues that tag
  names like `(P) Dave Price`.
  - The name without the tag goes in each driver's Nickname, and the
    overlays use it.
  - The timing screen and roster keep the full name, so class changes still
    show.
- **Classes from name tags**: `(P)`, `(SP)`, `(PA)`, `(AM)`, `(G)`, `(S)`, `(B)` and the like put
  drivers in the matching league class, by its name, its *iRacing classes*
  entries or its initials. Numbers and stripes on the overlays take the class
  colour, and the lap tracker's driver-number badge does too.

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
