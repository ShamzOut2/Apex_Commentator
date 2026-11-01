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

- Lap tracker: a sector just done shows its **difference** first (−0.324 /
  +0.512, against the driver's best, the class's or anyone's, as the
  reference is set), fading in and out on its colour for 3 seconds (you can
  set how long), then its time. A purple one gets a white light sweeping
  across it, a green one a soft pulsing lighter-green glow.

### Fixes

- Race control: the commands are sent in iRacing's chat by themselves; they
  used to sit in the chat box until you pressed Enter.

## v0.5.3

### New features

- Lap tracker: an **invalidated lap** shows: a line through the sector it
  happened in, the rest of the lap greyed out, and at the line every sector
  struck through and INVALID in place of the lap time, in colours you pick.

### Improvements

- Lap tracker: against the class or overall best, a purple sector turns
  green once someone else goes faster through it.

### Fixes

- Lap tracker: a sector on a lap that's then invalidated no longer counts as
  the fastest; whoever's fastest on a clean lap is purple instead.

## v0.5.2

### New features

- Boards: **Qualifying results** (a qualifying session of the event, by best
  lap, with gaps and intervals) and **Starting grid** (any race of the event,
  before anyone loads in: from qualifying, the previous race's finish or the
  grid walk's order, with a **reverse grid** of the top N, overall or in each
  class; as a list or as the cars line up). Every board setting the others
  have, and hotkeys.
- Championship: **overall points count as class points** (each class's table
  ranks its drivers on their overall points).
- Grid walk: the top and bottom rows of cars can be sized and moved on their
  own; the cards' size; the NOT ON TRACK tag can be turned off.
- Grid walk tab: **Names** and **Nicknames** (the grid walk on stream and the
  list on the tab).
- **Officials mode**: a League | Officials switch in the top bar, for an
  official or AI race: iRacing's own data on screen, none of the league's
  names, classes or rules (the league stays picked for switching back).
- Starting grid board: **row by row**, the front row first and the next row
  on a button or hotkey (or all at once); every driver and row comes in with
  its own animation, and the qualifying results wipe in from pole.
- Lap tracker: purple sectors can be the **fastest overall this session**
  (any class).
- Grid walk: each row's car pictures can be **turned** to line up with the
  boxes.
- Grid walk: moving on to the next pair, the new cars **slide in along the
  road** into their boxes as the last pair's slide on out, and each driver's
  card slides in from (and back out to) its own side of the screen.

### Improvements

- Grid walk: the car pictures go much bigger (up to 600%, and each row up to
  400% of that).

### Fixes

- Grid walk: the seconds per pair you set are kept (they went back to 8
  seconds) and used as soon as you type them.
- Lap tracker: times a replay of a session the app has already seen (it
  froze on OUT LAP), keeps timing through a second or two of the app being
  busy, and picks a lap up when iRacing's lap counter ticks over if the line
  crossing was missed.
- "Full name" now shows the full name everywhere (boards and overlays) with
  the league's "Remove driver class in name" on: the class tag comes off,
  but the name isn't swapped for the nickname (that's the Nickname style).

## v0.5.1

### New features

- Grid walk: **car picture size** of your own.
- A hotkey to put the **grid walk on your screen** (on the Overlays tab's
  screen).
- Boards: a **name style** for the drivers' names (full name, T. Smith,
  Smith T., last name…) on the championship, teams' and finishing order
  boards, as the calendar's winners already had.
- Grid walk drivers' cards: the driver card's choices (grid position overall,
  in class or both, class name with it, car number, class badge, team name
  and logo, car badge, class colour from the main or secondary class), and
  the qualifying **gap**, **interval** to the car ahead in class or lap time,
  also painted on the track if you like.

### Fixes

- The "everything on my screen" hotkeys put the overlays and boards on the
  screen picked in the Overlays and Boards tabs (keys that work from
  anywhere used the first screen).
- A board taken off screen keeps your own background as it fades out,
  instead of switching to the default one.
- Championship boards: a penalty now comes off the driver's class standings
  too when it was given to their roster entry and their results were saved
  under a slightly different name (capitals, spacing or a "(P)" class tag).

## v0.5.0

### New features

- **Custom points systems**: points tables of your own for different kinds
  of race (a sprint, a feature…), as many as you like, picked for each round.
- **Drop a race meeting as a whole**: its races count as one for the drop
  rounds and drop together.
- **Grid walk, rebuilt**: the grid in perspective from beside the track, with
  textured tarmac, kerbs, grass, a wall with advertising boards, catch
  fencing and a grandstand; the cars ahead wait up the road and the camera
  glides down the grid from pair to pair.
- Grid walk: **Auto-play** on or off (off: Next / Prev move it), a hotkey for
  the previous pair, and the name style and nickname as you like them.
- **Show all on my screen**, and hotkeys to put every overlay or the boards
  on your screen (or take everything off).
- Timing screen: name style (full name, D. Price…) and nicknames on or off.
- A hotkey for **everything off screen and back**: every overlay, the board
  and the grid walk go; press again and they come back.
- A hotkey to switch the timing tower's header between laps left and time
  left.
- Timing tower: the coloured bar can take its colour from the main or the
  secondary class on its own, separately from the car number.
- Teams: **✕** on a league under *Also in* takes the team out of that league.
- Timing tower: a **chequered flag** comes out on a tab at the tower's right
  edge, level with each driver's row, as they finish the race, and keeps
  waving.
- Grid walk: **Cars either side on the grid**, shown or hidden (just the
  pair).
- League builder: **—** in the main Class column, for a driver with no main
  class.
- Driver on camera: the class name with the class position can be turned
  off.
- **Eyedropper** by every colour box: click it, then click anywhere on your
  screen to take that colour (the colour picker's own eyedropper doesn't work
  in the app window).
- **Team logo size** for every overlay and board with team logos.
- Timing tower: **driver name column width** of your own (0 = automatic).
- Season calendar: tick which classes' winners show under past races.
- Timing tower: in a timed session, once the clock runs out the header shows
  LAST LAP (instead of going blank) until the chequered flag.

### Improvements

- Boards: gold, silver and bronze for places 1–3; an accent colour of your
  own, which you can pick from the colours of the board's background image;
  the league name in the header can be turned off; the Wins column is
  centred; the leader stays at the top of every page, the rest carrying on
  under them.
- Finishing order: the winner's Gap shows their laps or their race time.
- Season calendar: each card starts with the meeting's or round's name; each
  race has its own box with its name and length, and after it's run, each
  class's winner under it, one a line (the race and class names can be
  turned off).
- Rounds: the race length is a number of minutes, hours or laps.
- Standings tower: separate max drivers and extra drivers for Overall and
  By class; the extra drivers always fill every row as they rotate.
- Driver on camera: show the overall position, the class position or both.
- Pit stops: the position follows the standings tower (overall or in class).
- Championship battle and pit stops: a matching sleek entrance and exit.
- Every overlay and board now leaves with its entrance in reverse: sponsors
  fade out, lap trackers drop away, a board's rows slide back out and its
  header lifts away, and the grid walk's cards close before it fades.
- Grid walk: seen from high up at an angle across the grid, like a TV grid
  graphic, with each box's number and qualifying gap painted on the track;
  the drivers' cards look like the other overlays' (the driver-on-camera
  card).

### Fixes

- Timing tower: the dark background behind the header's text now covers the
  whole header, the same size as the chequered flag.
- The new fastest lap flash no longer shows a class name for a driver with
  no main class.
- Drop-down lists of drivers, teams and leagues are in alphabetical order
  (the Penalties tab's driver list, say).
- A penalty for a driver whose results were saved under another name for them
  (e.g. before their iRacing ID was in the roster) now comes off their class
  points as well as overall.
- Teams no longer end up in every league: sharing a team with one league
  doesn't share it with all the others that league shares with, and a
  league taken off a team stays off.
- Overlays in a session outside the league (practice, testing) no longer go
  empty: only drivers in the league's roster left without a class are
  hidden, not everyone who isn't in the roster. This also brings back the
  qualifying lap tracker there.
- Boards: the next page of a board keeps the board and its background in
  place; just the rows change.
- Hotkeys are kept by the app itself, so every window (the app, pop-outs, a
  browser) has the same keys and they survive updates. The Hotkeys window
  lists every key that's set at the top.

## v0.4.9

### Improvements

- Driver on camera: the card now leaves with an animation of its own, the
  entrance in reverse (details fade, a light sweep, the card closes to the
  middle and drops away).
- Season calendar board: a race meeting lists each of its races by name with
  its length (Race 1 · 20 min, Race 2 · 20 min, Race 3 · 40 min).
- Race gaps update more smoothly (the overlays get new numbers twice as
  often).

### Fixes

- Replays of a race watched after the server has moved on to the next
  session are shown as a race again: the class leaders' lap counter in the
  gap / interval column, race gaps and the race header.
- Race gaps in replays: no longer stuck or lagging. The app's own timing is
  kept for the whole race, so a replay of any lap (also after the flag)
  shows the gaps as they were, instead of iRacing's laggy ones.

## v0.4.8

### New features

- **Pit stops overlay**: when a car comes into the pit lane in a race, a card
  with its pit lane time (entry line to exit line) and its time in the pit
  box, ticking, and the final times for a few seconds after it leaves. Set
  how many drivers it shows at once, how long each driver's card stays up,
  and how long it stays after the exit line.
- **New grid walk**: a track across the screen with the two cars of each
  row in their staggered grid boxes and the drivers' details beside them,
  using your own car pictures: point the app at a folder of pictures named
  `iRacingID.Carname` (e.g. `123456.Porsche 911 GT3 R (992).png`) and each
  driver gets the right car and livery.
- **Import a sign-up sheet**: drivers, teams and classes from any spreadsheet
  (CSV): iRacing ID, name, car number, team and class are found by
  themselves, and you can check which column is which before importing.

### Improvements

- Round results can be imported from iRacing's own event result export
  (.csv): positions, laps, fastest laps, incidents, gaps and DNF / DNS, with
  the track and date for the round.
- Per-column opacity is now each column's background (with a colour of your
  own), not its text.
- Team logo and team name are columns of their own on the tower, the full
  screen and the boards, each on or off, the logo before or after the name.
- Driver on camera: the swap now swaps just the team logo and the car
  badge; the team name stays under the driver's name.
- Timing screen: a battle lights up steadily in your colour, and only the
  driver within the gap, not the car ahead.
- Timing tower: hotkeys for the sponsor bar and for overall / by class; the
  chequered flag header has one dark plate behind all its text.
- League builder: duplicate a league; change the order of sponsor logos.
- Standings and driver on camera: class colours from the driver's main or
  secondary class; a driver without one shows no colour (a plain number, no
  bar, no card background).
- Driver on camera: just the overall position (the class position is an
  option).
- Drivers with no class in the league (neither main nor secondary, e.g. a
  safety car) are left off every overlay and out of the results.
- Standings by class: the extra drivers show under each class.
- League builder and Teams: the arrow keys move between the boxes.
- The photo booth (taking car photos in iRacing) and the grid map and head
  to head grid walk styles are gone; the grid walk uses your own pictures.

### Fixes

- Lap tracker (qualifying and practice): laps are timed again in real
  sessions. A car's position stepping back a hair (iRacing smooths other
  cars' positions) dropped its lap, leaving it on "OUT LAP" with empty
  sectors.
- The timing tower's sponsor bar no longer flashes; it fades only when the
  next logo comes up.
- The tower's team logo is the same size before or after the name.

## v0.4.7

### New features

- **Move any overlay**: every overlay has Move right / Move down, to keep
  them clear of each other and fit your layout.
- **Sponsor logo bar** under the timing tower's header.
- **Race control tab**: give any driver a drive-through, stop & go or stop
  & hold (seconds, minutes or laps), clear one driver's or everyone's
  penalties, set the grid time, start the race and message every driver,
  straight to iRacing (you need to be a session admin).
- **Hotkeys that work from anywhere**: give a camera, overlay, board or the
  grid walk a key with Ctrl or Alt (e.g. Ctrl+Alt+1) and it works whichever
  program is in front, iRacing and OBS included. Plain keys still work in
  the app's own windows.
- **Hotkeys for overlays and boards**: a key for each overlay (on / off),
  the grid walk and every board (on screen, and off again), set in the
  Hotkeys window, now also on the Overlays and Boards tabs.
- **Championship battle overlay**: pick two to six drivers (or the car on
  camera and the cars around it, or the top 3) in any championship, overall
  or a class, and show their places, points and the gaps between them; live
  during a race, with the points this race would give them.
- **Board pages**: set how many drivers each board shows a page, and go
  through the rest with Next / Prev (or hotkeys) until the end.

### Improvements

- Finishing order: Gap and Interval columns; DNF, DNS and DSQ show there
  instead of a column of their own.
- Board backgrounds: an image fills the whole screen at its own size again,
  whatever the board's size.
- Timing tower and full screen: "LEFT" after the time left can be turned
  off, and the accent colour (time / lap, the header's bar and line) can be
  your own or follow the session: white practice, purple qualifying, red
  race.
- Standings (tower and full screen): the leader's interval can show
  "Leader" or the lap they're on, like the gap column.
- Heat racing: heats, the consolation and the feature are recognised, can
  have names of your own, and on the day of a heat event each race takes the
  name of its league round for that date, with its results saved to that
  round.
- The tabs are in a new order: Home, League builder, Teams, Championship,
  Timing, Grid walk, Overlays, Boards, Race control.
- Finishing order: a button for every class of the league, secondary
  classes and classes without points of their own included.
- The finishing order board can show any session of the event in iRacing:
  practice, qualifying, warm-up, each heat or the race (practice and
  qualifying by best lap, without points).
- Standings (tower and full screen): put the team logo before or after the
  team name.
- Driver on camera: swap the team and the car badge (badge under the name,
  team at the end), and put the team logo before or after the team name.
- Driver on camera: set how long the card stays on screen (1 to 120
  seconds), or keep it up while they're on camera. A new driver replaces the
  card and starts the time again, picking the same driver again in the app
  brings their card back, and it now goes on time even with iRacing paused.

## v0.4.6

### New features

- **Race results save themselves**: when a race is over (or the session
  moves on), its finishing order, with DNFs, DNSs and the points, goes into
  the championship round it counts as, so the standings are ready to show
  straight after the race. It can be turned off in Calendar & results.
- **Secondary classes score how you choose**: on where their drivers finish
  among each other, or the points they score in their own class, or
  overall. A driver in two classes scores in both (and overall), each on
  its own points, and the round results show each.
- **Teams in more than one league**: in the team builder, tick the other
  leagues a team races in. The team and its drivers are set up there too,
  and drivers who join one of those leagues later are put in their team
  automatically.
- **Custom opacity per column** on the standings (tower and full screen) and
  the championship, teams', manufacturers' and results boards: tick it and
  set each column's opacity.

### Improvements

- Championship scoring is clearer: tick **Class championships** and/or an
  **Overall championship**, each with its own points table, so overall
  points can differ from class points and both run at the same time.
- Photo booth: **Only cars without a photo yet** skips drivers who already
  have a car photo, and **Photograph drivers as they load in** takes each
  driver's photo automatically a few seconds after their car loads in
  (never during a race once it's green).
- Turn rounds into race meetings (and back) on the fly: one round at a
  time, or every round at once, e.g. after building the season from a
  calendar. A round's results stay with the meeting's first race.
- Leagues are set up by hand or from the session you're in: the iRacing
  login (loading a league by its League ID, building rounds from the
  iRacing season, fetching the official track list) is gone, and with it
  the API settings. Existing leagues are unchanged.

### Fixes

- "Show on my screen" overlays covered the whole screen in some cases. Each
  overlay's window is now cut down to the overlay itself (the tower, the
  driver board…), so the rest of the screen is never covered and the mouse
  goes straight through, and it's made see-through the way the Apex
  Overlays app does it. The log (`%APPDATA%\Apex Commentator\apex.log`)
  notes each overlay put up.

## v0.4.5

### New features

- **Build the season's rounds from a calendar**: from the league's season in
  iRacing, by scanning the league's calendar image, or from its text pasted
  in. Check and correct the rounds found, then make them all at once.
- **Race meetings** for leagues that run several races in one event (heat
  races) and count each as a round. Import every race of the event in one
  go, and the calendar board shows the meeting as one.
- **Secondary classes**: a driver can be in a second class as well as their
  main one (e.g. a Rookie Cup or Pro-Am trophy). It works in the background:
  the overlays show the main class, and the secondary class gets its own
  championship, standings, results and board.
- **Class and overall points added together**: a new way to score, where
  each driver gets the points for their class position plus the points for
  their overall position. Any class can also have its own points table.
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

- Car badges and team logos no longer sit in a white box anywhere. Team logos
  that come with a white background show without it, and dark badges and
  logos are shown light so they stand out on the dark panels.
- Choose the order of the columns on the standings tower and on the
  full-screen standings: drag them, or use their arrows.
- The League builder is tidier: its settings are on three tabs (Drivers,
  Classes, and Logos, banners & sponsors), with shortcuts to Teams and the
  season. The driver list has room for full names and teams.
- Overlay and board settings are tidier: each is split into short sections
  (What it shows, Header, Columns, Drivers…) that open and close, and the app
  remembers which you left open. Settings that depend on another (like the
  red-interval threshold or the fastest lap flash timer) only appear when
  that one is on.
- Pick the screen for **Show on my screen** once, at the top of the
  Overlays tab or the Boards tab, instead of under every overlay. It's
  remembered, and changing it moves whatever is already up.
- The season calendar board can show your own round names ("Round 3 ·
  Spa 6 Hours", just the name, or just "Round 3"). Dates can be shown as
  Sun 22 Nov, 22/11/26, 22nd November, 22nd November 2026 or Sunday 22nd
  November. The "×2 points" note on rounds worth more can be turned off.
- The Overlays tab is shorter: the preview panes are replaced by a
  **Preview ↗** button that opens an overlay in its own window.
- The standings' column headings (GAP, INT…) can be turned off, and the
  race leader's gap box can show the lap they're on ("Lap 12") instead of
  "Leader".
- The standings (tower and full screen) can turn off the coloured bar by
  each driver, and the background behind the car number (it's in the
  driver's class colour when on).
- When the chequered flag comes out, the standings header turns into a
  waving black-and-white chequered flag, on the tower and the full-screen
  standings. It flashes in, then keeps waving until the session changes or
  the overlay is taken off.
- The extra drivers under the Overall tower's top rows can rotate through
  the rest of the field, a few at a time on a timer, then start again. They
  can also be dimmed with their own opacity.
- The standings header (tower and full screen) can hide the series name
  and/or the track name, and the session names can be your own (e.g.
  "FEATURE RACE" instead of "RACE"). A long session name can wrap onto two
  lines, or stay on one line with the tower widening for it.
- The standings tower's width fits its contents: each column (the name
  column too) is as wide as what's in it, so there's no big empty gap. Or set
  the width yourself in pixels.
- Sort the League builder's driver list by clicking a column heading (name,
  customer ID, car number, driver number, nickname, team, notes, class or
  car). Click again for the reverse order, a third time for the original
  order.
- The Timing tab's **LIVE** button sits with the replay buttons instead of
  at the far end of the bar.
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
