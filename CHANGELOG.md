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

- Font for every overlay and board (Widget Settings → All overlays & boards):
  the 20 fonts from Apex Overlays, bundled, and Bahnschrift. The text is
  sized to fit, so nothing changes size with the font.

### Improvements

- Update pop-up: a few versions behind, it shows every version's changes
  since yours (and how many), even when GitHub's list of releases can't be
  had just then.
- Replay bar: an Open folder button for the replay data check's files.
- On-track battle: a car joins or leaves the list once it's been within (or
  outside) the gap for a moment (1.5 s to start with, 0–3 s), so it no
  longer flashes in and out at the edge of the gap.

### Fixes

- Gaps and intervals on the tower and Timing Screen no longer jump about
  with iRacing's patchy position updates for other cars.

## v0.7.1

### New features

- Replays: when iRacing's car data stays live during a replay (the app finds
  out when a replay is paused mid-race, or set it on the replay bar), gaps,
  intervals, places and the race log go on live during replays.
- Record check (replay bar): what iRacing sends, once a second, saved to a
  file, to see what stays live during a replay.

## v0.7.0

### New features

- Timing Screen: a pill at the top or bottom of the list when a battle is
  scrolled out of sight; click it to go there.
- Timing Screen: 1 list or 2 lists side by side, to fit a big field on one
  page.
- Team championship: drop rounds can apply to the drivers only, with every
  round counting for the teams.
- Grid walk car pictures can have the driver's class tag in front
  (`PA.123456.Car name.png`), matched to the tag in brackets in their name.

### Fixes

- Starting grid: the grid iRacing sets for a race (a reverse grid
  included), from the race's session starting, before anyone has joined the
  track, with nothing to set; before that, worked out as before.
- A race meeting's races show only their round's own name, never with
  "Heat 1" added, and keep it after the race.

## v0.6.9

### New features

- Car manufacturer logos: a Car column on the timing tower, the full-screen
  standings and the Timing Screen.
- Current stint: a Stint column with the laps each car has done since it
  last pitted (PIT while on pit road).
- Hotkeys to show or hide each timing tower and standings column.
- Starting grid: a "Current positions" grid source, for the order the cars
  are lined up in on the grid.
- Sponsors: the pinned logo can sit on the right instead of the left.
- Several fastest laps close together: show them side by side, or one after
  another, instead of the newest cutting off the last.
- Colours: class, group and accent colours stay solid on see-through panels
  (General settings, on by default).

### Fixes

- The race log now keeps every incident of the whole event, not just the
  last 300.
- Pit stop counts: leaving the pit stalls for the grid, and stops from an
  earlier session, no longer count.
- Timing tower extra drivers: the last set shows only the drivers left, with
  blank rows, instead of wrapping back round (P14 above P4).
- Gaps no longer jump about after watching replays during a race.
- The driver on camera board changes with the camera straight away, instead
  of about two seconds after the cut.

## v0.6.8

### New features

- Race meetings: set each meeting to a single race, a 2-race heat (heat,
  feature) or a 3-race heat (heat, consolation, feature). Its rounds then go
  with those races in order, and their names replace iRacing's race names on
  stream.
- A driver changing class mid-season: as for a team change, their points so
  far stay in the class they raced in, or move with them from the race you
  pick.
- Teams championship: a race meeting can count as one (each team's best N
  over the whole meeting), and the "all drivers added together" or "best N"
  choice is clearer.
- On-track battle: the driver you're spectating and every car within the gap
  you set, ahead and behind; their class only or overall; and gaps to the
  car ahead or to the driver you're spectating.

### Fixes

- Race meetings: when iRacing runs a second heat, it's no longer counted in
  the live championship as the feature's race, or saved into the feature's
  round (or a new round) when it ends.
- Timing tower and Timing Screen: a car towed to its pit box no longer jumps
  to the top. iRacing counts a tow to a pit box just past the line as being
  on the next lap; the app now goes by the laps the car has completed.
- Opening the qualifying results or starting grid board with iRacing not
  connected no longer breaks the app until it's restarted.
- Race meetings: when iRacing splits the field into more heats (or adds a
  consolation), the feature still gets its round: its race name and its
  reverse grid.
- Timing tower and live timing website: after a timed race's clock runs out
  it stays LAST LAP until the leader finishes, rather than going back to a
  timer when iRacing counts down the time left to finish.
- Boards: the text size setting now changes the drivers' rows too, not just
  the heading.
- Widgets tab: "Hide board" is no longer right next to the on-your-screen
  button, which is now "Off my screen".

## v0.6.7

### New features

- On-track battle widget: the car on camera and the cars just ahead and
  behind it ("Battle for P3"), with their gaps. It can come up by itself
  whenever the car on camera is in a battle.
- Track map widget: the track's outline with no background and a dot for
  every car, in its main or secondary class colour.
- Each league keeps its own widget settings, brought in as you pick the
  league. You can copy another league's in Widget Settings.
- Sponsors: one sponsor can stay on screen while the others rotate beside it.
- Custom points systems can have their own bonus points.
- Timing tower: an option to hide the drivers during a replay, leaving just
  the header saying REPLAY.

### Improvements

- Replays during a race: the tower, Timing Screen, live timing website and
  widgets keep the live race's order, gaps, intervals and laps down however
  long you watch, re-timed at the line each time a car crosses it.
- Starting grid board: the name plates grow to fill the page however many
  drivers are on it, and can be made bigger or smaller by hand.
- Decimal places of gaps and intervals can be set from the timing tower's
  settings and the Timing Screen's toolbar too.

### Fixes

- Timing tower: the header no longer flashes white (last lap) as a timed race
  goes green.

- Timing tower: in a timed race, the chequered header and the finish flags by
  drivers' names wait for the leader to cross the line. A car further back
  crossing first no longer gets a flag: it has a lap more to go. The header
  says LAST LAP until the leader finishes.

## v0.6.6

### New features

- Live timing tab: the spectators' website has a tab of its own, with a live
  preview and settings for its heading and colour, name style, team names and
  logos, car numbers, which columns show, the Driver tracker and the map's
  labels.

### Fixes

- Live timing website: when Cloudflare's tunnel can't start, the link no
  longer shows Cloudflare's own address as if it were yours.

## v0.6.5

### Improvements

- Live timing website: cars move smoothly round the track map instead of
  stepping and catching up, and the page does less work, so it keeps up
  better on phones.

### Fixes

- Timing tower and Timing Screen: the leader's interval shows "Leader"
  instead of being blank. You can still pick their current lap or nothing in
  the tower's Widget Settings.
- Timing tower and Timing Screen: names no longer jump around at the end of
  a race. Drivers who've finished keep their places as they park or leave,
  and the cars still racing stay in order round them.

- Timing tower: the fastest lap stopwatch stays with the driver who set it.
  When they leave it no longer jumps to whoever is quickest of those still
  there; only a quicker lap moves it.

## v0.6.4

### Fixes

- On-screen overlays no longer cover the screen with a dark, blurred
  background when Windows is in dark mode: Windows 11's frosted backdrop
  (Mica) is switched off on them, and kept off. The colour key way of
  making them see-through is only tried after you answer No to "Can you see
  your screen through the overlay?".

## v0.6.3

### New features

- **Live timing website** for spectators (Home tab): a page anyone can open
  in their browser with the running order, a head-to-head of any two drivers
  and a track map with every car on it. It goes out through Cloudflare, so
  nobody sees your PC's address, and it only shows the timing: never
  iRacing IDs, notes or anything about you.

## v0.6.2

### New features

- League builder: **⇆ Copy settings from…** brings another league's
  settings into this one in a couple of clicks: points and rules, classes,
  teams, logo, banners and sponsors, the calendar (without results) and
  options, each ticked or not. Drivers and results stay as they are.

- **All overlays & boards** in Widget Settings: how many decimal places
  gaps and intervals show (live race, and qualifying / results), and what
  the overlays do while a board is up: stay, dim or hide.
- Every overlay and board has a **Text size** next to its Size, and its
  background opacity works on the default look too: turn a board's down
  and the race shows through it.
- **Tyres**: a small tyre shows what each car is on, white for dry and
  blue for wet, on the timing tower (and its full screen), the driver card
  and the Timing Screen.
- Teams: **Leave out of the team standings**, for a team that shouldn't be
  in the team championship (its drivers still score for themselves).
- Sponsors overlay: **Stay up**, so it isn't put away with everything else
  and isn't dimmed or hidden while a board is up.

### Improvements

- Race log: crashes are spotted and shown as a red **ACCIDENT** (contact
  followed by a car slowing, spinning or going off, a heavy hit, and every
  slowdown); iRacing's warning now reads **SLOW DOWN**.
- Timing Screen: **⏮ Incident / Incident ⏭** step through the incidents in
  the race log (the first press from live replays the latest one) and pick
  each in the log.
- Co-commentator: a **FREE | SYNC** pill in the top bar and on the Timing
  Screen shows which you're on; click it to switch. **⧉** puts the switch
  in a small window of its own on top of iRacing, to click without going
  back to the app.
- Lap tracker: sectors are compared with the **Session overall best**,
  **Session class best** or **Session personal best**. Purple beats that;
  green only when it beats the driver's own best; yellow when it's slower
  than their own best at all.
- Lap tracker: when the camera moves, the big tracker changes over to the
  new driver in place, and there are never more small trackers on screen
  than set (several laps ending at once no longer swaps them in and out).
- Starting grid board: fewer **drivers on screen** make bigger name plates;
  and row by row can **scroll**, the top row sliding up and off as the next
  one comes in, instead of turning to a new page.
- Grid walk: it goes in the starting grid board's order, reversed grid
  included; a car with no picture leaves its grid box empty instead of
  being drawn.
- Starting grid board and grid walk: qualifying times and gaps only show
  when the grid is from qualifying.
- Watching a replay mid-race: the race log goes on logging live incident
  points and the places gained at the line (iRacing's results keep coming),
  and says so; the tower and Timing Screen keep their live order.
- A driver who leaves the race shows a small **OUT** tag in place of their
  gap and interval, on the timing tower, its full screen and the Timing
  Screen.

### Fixes

- Boards: the leader's Gap and Int are no longer empty. Qualifying
  results: pole's lap. Starting grid: each class pole's lap. Race results:
  the winner's whole race time or their laps completed (**The winner's Gap
  and Int show**; their laps where iRacing hasn't given a time), with
  everyone else's gaps measured from the race times.

- Overlays' and boards' opacity setting now makes the whole overlay or
  board see-through (its backdrop, panels, rows, class colour boxes, number
  boxes, stripes, sector bars and borders) while the text stays solid;
  before, only some parts faded.

- On-screen overlays that came up solid on some PCs (Windows'
  transparency effects off, for one): answering **No** to "Can you see
  your screen through the overlay?" now tries another way of making them
  see-through before giving up.
- Lap tracker: a lap no car could do (a tow or reset mid-lap) is thrown out
  instead of becoming an impossible personal best (an 8 s lap) that put
  every colour wrong.
- A car towed to the pits (or leaving) mid-race no longer jumps to the top
  of the timing tower and Timing Screen.
- After the leader takes the flag, everyone still racing keeps being timed
  live (places and gaps) until they cross the line themselves.
- Gaps (and so intervals) show from the very start of the race, instead of
  0.0 until the second lap.
- Timing tower: a driver who's taken the chequered flag keeps their place
  (and gap) from the moment they crossed the line, whatever they do after:
  pitting, going to the garage or leaving no longer greys them out or moves
  them.

## v0.6.1

### New features

- **Team changes mid-season**: change a driver's team after they've raced
  and pick their first race for the new team (the races before it stay
  with the old team), or move all their points to the new team. **⇄** by
  their team on the roster sets the team for each race one by one. Each
  race result now keeps the team it was raced for.

## v0.6.0

### New features

- **Dual commentary**: a co-commentator's app can follow your camera.
  Tick *Let a co-commentator follow my camera* (Home) and give them the
  address and code shown; whatever driver and camera you put on (from the
  app, a hotkey or iRacing), live or a replay, their iRacing shows too.
  **Free mode** lets them go their own way (a replay, another driver) and
  **Sync** takes them back with you (top bar, or hotkeys).

## v0.5.9

### New features

- **Widgets** tab: every overlay and board on one dashboard, a card each
  with big Show / Hide buttons and the settings that change most (name
  style, overall / by class, header…), the boards along the bottom, and
  All off / back.
- **Widget Settings** tab: every setting of every overlay and board, picked
  from a list on the left, laid out label | value in sections, with its OBS
  links and a live preview. (These two replace the Overlays and Boards tabs.)
- **Delay**: the race shows 1 s behind iRacing in the app and on every
  overlay (Timing Screen, next to the battle settings; 0 turns it off).

### Improvements

- Timing tower: drivers who leave the session stay where they were, greyed
  out (the same setting as the full screen's).

### Fixes

- Starting grid (Automatic): every race after the first (a two-race
  round's second race, a consolation, a feature) starts from the race
  before's finish, also when it's an iRacing event of its own (from the
  saved results); a meeting's reverse grid stays on when the session moves
  on. With no qualifying in the event, the grid iRacing lines up.
- Finishing order board: gaps no longer go missing when the winner has no
  race time (just after the flag, an earlier heat, a replay); an earlier
  race without iRacing's race times uses the app's own gaps at the finish.
- Timing tower in a replay: no more made-up gaps (every gap showing 1.0):
  during the race it keeps the live gaps, after it the replay's own (or
  none where the app has no timing for that moment).
- Timing Screen: before the start, drivers are listed in starting grid
  order (not at random); places gained count from that grid.
- Driver on camera: no longer flashes the last driver as the camera cuts.
- Timing Screen: a battle lights just the interval cell, not the whole line.
- Race log: **Hide…** leaves kinds of event out (incidents, warnings…).
- An event with two (or more) races, called RACE by iRacing, now takes its
  rounds' names on the tower, the starting grid and the finishing order
  board, without changing them by hand, even when the rounds aren't dated
  that day (it takes the meeting marked Live, else the next one to be run).
- Drop rounds count straight away: changing the points rules (drop rounds
  included) in the Championship tab applies them to the standings, boards
  and overlays at once, without pressing Save.
- Drop rounds now apply to the teams' and manufacturers' championships too.
- Race meeting rounds: the box for how many cars are reversed is always
  there next to *Reverse grid*.
- In a replay during a race, the standings (tower, Timing Screen, live
  championship) stay on the live race instead of showing the replay's.
- Cars crossing the line no longer jump a lap back or forward for a moment.
- Live championship standings: a car off the track for a while (towed, in
  the garage) keeps its place instead of counting as out.

## v0.5.8

### Improvements

- Lighter on the PC with several overlays open: each update is prepared
  once for every page (the app, pop-outs, each overlay in OBS) instead of
  once per page, and is smaller.

### Fixes

- An error while preparing an update no longer freezes every overlay and
  the app until it's restarted: the app carries on and logs it.
- Overlays and the app reconnect by themselves if their connection to the
  app stalls (after the PC sleeps, say), instead of needing a reopen.
- The log file (apex.log) no longer grows without end: past 5 MB it's
  trimmed to its latest part.

## v0.5.7

### New features

- Starting grid: **Automatic** grid for race meetings: the heats from
  qualifying, the consolation from the heat before it, the feature from the
  consolation (the others stay there for when it's needed).
- Race meeting rounds: a **Reverse grid** box with how many from the front
  are turned round; the starting grid board follows it.
- Timing tower: the header turns white on the final lap (or LAST LAP), then
  into the chequered flag at the finish.
- Timing tower: watching a replay, the header is just REPLAY, in the
  middle, on the accent colour.
- Drivers who leave the session can stay listed: on the Timing Screen
  (marked LEFT) and on the full-screen standings (where they were).

### Improvements

- Starting grid board: its title is the race's name as the tower gives it
  (the round's name, or your names for heats, consolation and feature).
- Timing tower: the finish flag tick box is in the tower's Drivers settings
  (it was under Fastest lap).

### Fixes

- Timing tower: the chequered flag no longer comes out mid-race in the next
  iRacing event after one the app already saw finish.
- Timing tower: the chequered flags by finished drivers no longer flash in
  again every time the tower updates.
- Timing Screen: the flag column's chequered flag stays put instead of
  flashing on and off.

## v0.5.6

### New features

- Timing tower: the coloured bar can show the driver's team colour
  (*Coloured bar's colour from*).
- Timing tower by class: tick which classes show (one, some or all) and
  put them in the order you want.

### Fixes

- Timing tower: by class, the coloured bar shows the class colour picked for
  it again, not the team's colour.

## v0.5.5

### Improvements

- Lap tracker: trackers open out from the middle with a light sweep and
  close the same way, a finished lap's time pops in with a purple (fastest)
  or green (personal best) glow, and the small trackers slide when they
  change places.

## v0.5.4

### New features

- Lap tracker: a sector just done shows its **difference** first (−0.324 /
  +0.512, against the driver's best, the class's or anyone's, as the
  reference is set), fading in and out on its colour for 3 seconds (you can
  set how long), then its time. A purple one gets a white light sweeping
  across it, a green one a soft pulsing lighter-green glow.

- The "everything off screen and back" hotkey has two more alongside it:
  one for the **overlays** (and the grid walk) only, one for the **board**
  only, which brings back the same board as it was (the qualifying results
  and the starting grid included, the grid's rows shown and all).
- A hotkey for the **championship battle** with the drivers picked in its
  settings: on screen, and off again.
- Starting grid **hotkeys**: the grid on and off, full grid / row by row (or
  a key to switch), next row, back a row, every row, and the boards on your
  screen and off it.

### Improvements

- **Hotkeys** is a tab of its own (and a box on the Home page), next to Home;
  Race control moves between Championship and the Timing Screen (the Timing
  tab's new name).

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
