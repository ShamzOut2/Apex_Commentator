# Apex Commentator

A lightweight iRacing overlay suite for commentators. It runs a small local web
app next to iRacing. Open it in a browser on a second monitor, or add it as an
OBS dock.

- **Timing screen**: one screen for the race. Live standings with overall
  and class position, places gained or lost, gap and interval, flags and
  penalties. **Battles** (a car within 0.15 s of the one ahead) light up in a colour you choose.
  Click a driver to put the camera on them. A **race log** records
  overtakes, offs, spins, places lost, pit stops, penalties and fastest laps:
  pick a line and replay it from 5 to 30 seconds before. Camera buttons with
  your own hotkeys sit along the top, and replay controls and **LIVE** along
  the bottom.
- **League builder**: set a league up from the drivers in the current
  session, or add drivers by hand. Add nicknames, teams, team
  logos, notes and car and helmet photos. Define **classes** with your own
  names, colours and logos.
- **Grid walk**: an on-stream graphic that walks the starting grid two drivers
  at a time: the grid seen in perspective from beside the track, each car in
  its grid box (your own car pictures, matched to each driver and car) with
  the driver's details beside it. It advances on a timer you set, or when
  you press Next.
- **Standings overlay**: a timing tower for stream, overall or by class. In
  qualifying it starts empty and fills as drivers set clean laps.
- **Qualifying lap tracker**: live sector bars (purple, green, yellow) and lap
  clocks along the bottom of the stream. A big tracker shows the car on camera,
  with the lap time and gap to the driver's best when the lap is done.
- **Team builder**: teams with logos, short names and colours, and who drives
  for whom. They show on every overlay.
- **Championship**: each league's season with your points system, bonuses,
  drop rounds, class and team championships and post-race penalties. Results
  can be imported from the session, and live standings show the championship
  as if the race finished now.
- **Race control**: penalties for any driver (drive-through, stop & go,
  stop & hold, clear), the grid timer, starting the race and messages to
  every driver, sent to iRacing as its admin commands.

The tabs, in order: Home, Hotkeys, League builder, Teams, Championship, Race
control, Timing Screen, Grid walk, Overlays and Boards.

![timing screen: camera bar, standings with battles, race log, replay controls](docs/timing.png)

## What's new

<!-- whats-new:start -->
**Coming in the next update**

### New features

- Timing tower: the coloured bar can show the driver's team colour
  (*Coloured bar's colour from*).

### Fixes

- Timing tower: by class, the coloured bar shows the class colour picked for
  it again, not the team's colour.

Every version's notes: [CHANGELOG.md](CHANGELOG.md).
<!-- whats-new:end -->

## Install (Windows)

1. Download **`ApexCommentator-Setup-<version>.exe`** from the
   [latest release](https://github.com/ShamzOut2/Apex_Commentator/releases/latest).
2. Run it. It installs for your Windows user, with no admin rights needed. The
   installer isn't code-signed yet, so Windows SmartScreen may warn you:
   choose *More info → Run anyway*.
3. Start **Apex Commentator** from the Start menu or the desktop icon. Join or
   spectate a session in iRacing and it connects automatically. It
   reconnects if iRacing restarts.

No iRacing handy? Use the **Apex Commentator (demo mode)** shortcut for a
simulated race.

The control panel opens in its own window. This uses the Microsoft Edge
WebView2 runtime that comes with Windows 10 and 11. Without it, the app opens
in your browser instead. Your settings and leagues are stored in
`%APPDATA%\Apex Commentator` (`config.json` and `data\`), and a log is kept in
`apex.log` there. A portable zip is attached to each release too, if you
don't want to install.

## Run from source

Requires **Python 3.9+**.

```bat
git clone https://github.com/ShamzOut2/Apex_Commentator
cd Apex_Commentator
start.bat
```

`start.bat` installs the dependencies (`pyirsdk`, plus `pywebview` for the
app window) and starts the app. From source, `config.json` and `data/` live
in the project folder.

`start-mock.bat` (or `python -m apex --mock`) runs a simulated race. It
works on any OS, and `--mock-speed 5` speeds it up. Other options:
`python -m apex --help` (`--port`, `--host`, `--no-window` to use the browser,
`--config`). `--mock-session qualify` simulates qualifying instead, for trying
the lap tracker. `--mock-laps 10` ends the simulated race after 10 laps, for
trying championship imports.

### Using it from another PC or in OBS

- **Second PC on your LAN:** set `"host": "0.0.0.0"` in `config.json`, then
  open `http://<iRacing-PC-IP>:8180` from the other machine. The overlay
  has no login, so only do this on a network you trust.
- **OBS:** *Docks → Custom Browser Docks*, URL `http://localhost:8180`. The
  layout compacts itself for narrow docks.

## Timing screen

**⧉ Pop out** (next to *Hotkeys*) opens the timing screen in a window of its
own, without the tabs, so it can sit on another monitor while the main window
shows something else. Camera hotkeys work in whichever window has focus.

- **Standings**: Pos (overall), Cls (position in class, underlined in the class
  colour), **+/−** (places gained or lost since the start, within the class
  when a class is picked), car number, driver and team, lap, gap to the
  leader (timed by the app: how long ago the leader was where the car is
  now, so it updates continuously, keeps step with the order and keeps
  counting while a car is slow or stopped; "+1 L" for lapped cars), interval
  to the car ahead, last and best lap, pit stops, flag
  (yellow, blue, white, chequered), penalties (black flag, DQ, meatball,
  warning) and incident points. **Click any driver** to put the camera on
  them. The class chips show one class at a time, with gaps and places within
  it.
- **Battles**: a driver within the battle gap of the car ahead (0.15 s by
  default) is lit up, steadily, in the colour you pick: just that driver,
  not the car they're closing on. Both settings sit above the standings.
- **Names**: the name style in the list (full name, D. Price, Price D., last
  name), and **Nicknames** by the names on or off. Next to the battle
  settings, kept for this PC.
- **Race log**: everything that happens, newest first, filterable: overtakes,
  off tracks, spins, incident points, places lost after an off, pit in/out
  (with stop time and places lost), penalties and class fastest laps. **Click
  a line**, then pick how far back to start the replay: −5 s, −10 s and so
  on up to −30 s. The camera follows that driver. The line above the log shows
  whether logging is running: it logs live races and saved replays you play,
  and pauses while you rewind over something already logged.
- **Cameras**: one button per iRacing camera, plus Ahead, Behind, Leader,
  Exciting and Incident cam. *⌨ Hotkeys* sets a key for each camera; out of
  the box, 1–9 are the first nine cameras.
- **Replay bar**: rewind the car on camera by a set time (5 s steps), step
  through iRacing's incident markers, pause, play, slow motion, and **LIVE**.

### Keyboard shortcuts

| Key | Action |
| --- | --- |
| `1`–`9` (or your own) | Camera hotkeys |
| your own | Overlays on / off, grid walk, boards (see below) |
| `L` | Back to live |
| `R` | Rewind the car on camera (by the rewind setting) |
| `↑` / `↓` | Watch the car ahead / behind |

**Hotkeys for overlays and boards.** The **Hotkeys** tab (also on the Home page,
and the *⌨ Hotkeys* buttons on the Timing Screen, Overlays and
Boards tabs) also sets keys for:
- each overlay: the standings tower, lap tracker, driver on camera,
  sponsors, championship battle and pit stops, on and off;
- everything at once: every overlay, the board and the grid walk off
  screen; pressed again, whatever it took off comes back (with nothing up,
  every overlay comes on). Or apart: the **overlays** (and the grid walk)
  only, or the **board** only, which brings the same board back as it was
  (any board: the qualifying results and the starting grid too, its page
  and the grid's rows shown);
- the timing tower: its sponsor bar under the header on and off, overall /
  by class, and its header between laps left and time left;
- the championship battle: on / off with the drivers picked in its
  settings, and its quick picks (the car on camera and the one ahead, the
  cars either side, the top 3), which also put it on screen;
- the grid walk: on / off (starting from P1), and the next and previous pair;
- the starting grid: on / off (Overall, for the race on now or next), full
  grid or row by row (a key for each, or one to switch), next row, back a
  row and every row, and the boards on your screen or off it;
- on your own screen (app window): every overlay, the boards, the grid
  walk, or taking everything off (see "Overlays on your own screen");
- every board in the Boards tab (each class's standings, teams',
  manufacturers', the calendar, finishing orders), its next and previous
  page, and taking the board off screen. A board's key puts it on screen; pressed again while it's up, it
  takes it off.

A key does one thing: giving it to something else takes it off the first
(cameras included). Board keys show on the board buttons.

**Keys that work from anywhere.** A plain key (`1`, `C`…) works when an Apex
Commentator window is in front (pop-outs too). A key pressed with **Ctrl**
or **Alt**, and Shift if you like (e.g. `Ctrl+Alt+1`, `Ctrl+Shift+C`,
`Alt+F5`), works whichever program is in front, iRacing and OBS included,
for cameras as much as boards and overlays: the app registers it with
Windows and does the action itself. These show 🌐 in the Hotkeys window,
and are kept for the next start. One another program already uses is
shown in red: pick another. Letters, numbers, the number pad and F1–F24 can
be used this way. (On keyboards where Ctrl+Alt is AltGr, a Ctrl+Alt key
can't be typed in other programs while the app is running; Ctrl+Shift
combinations avoid that.)

## Race control

The **Race control** tab runs the session from the app. Everything goes to
iRacing as its admin chat commands, typed into the sim's chat and sent for
you (no need to press Enter), so you need to be an admin of the session in
iRacing (the host, or promoted by the host). iRacing must be open on this PC.

Along the top:
- **Clear all penalties** (`!clearall`), after a check that you mean it.
- **Grid time**: type the minutes (1 to 60) and **Set grid time**
  (`!gridset 5`): the race starts after that long instead of when everyone's
  on the grid.
- **Start race** (`!gridstart`): starts it now, whatever the grid time.
- **Message to all drivers**: type it and **Send to all** (or Enter).

Below, every driver in the session (find one by name or number), with:
- **Clear**: clears their penalties (`!clear #10`);
- **Drive-through** (`!black #10 D`);
- **Stop & go** (`!black #10`);
- **Stop & hold**: type how long and pick **Seconds**, **Minutes** or
  **Laps**, then press it (`!black #10 30`, minutes sent as seconds, or
  `!black #10 L2` for laps).

**Sent** on the right lists what's gone to iRacing, newest first. If nothing
happens in the sim, check you're an admin of the session.

## How replays work

The overlay watches telemetry for **every** car, so this works when you
spectate. It records:

| Event | How it is detected |
| --- | --- |
| **Overtake** | In a race under green, cars close on track swap order *and stay swapped* for 1.5 s, with both on track. Swaps from pit stops, offs or side-by-side jostling don't count. The event is timestamped when the pass started. |
| **Off track** | A car's track surface changes to off track. |
| **Slowdown** (SLOW) | A car's speed collapses relative to its recent pace *and* it's well under the usual speed at that point of the track, so braking hard for a hairpin doesn't count. The app learns each corner's usual speed from the cars going through it. Ignored on pit road and under caution. |
| **Spin** (SPIN) | A slowdown or off track where the car also rotates sharply within 0.2 s. iRacing only sends a car's heading for the car driven on this PC, so for that car it's the heading turning 45°+ in 0.2 s. For every car, it's the steering snapping 180°+ of opposite lock in 0.2 s, or the car travelling backwards along the track (it has turned round). Without any of these, the moment stays a slowdown or off track. |
| **Contact** (CONTACT) | Two cars touching. iRacing doesn't report contact between other cars, so the app looks for two signs. First, a car closing fast on the one just ahead (within a few metres) that suddenly stops closing within 0.12 s: the jolt of a hit, quicker than any braking. Second, a driver getting 4x (iRacing's car-contact incident) while another car was right next to them. That car is named, and the other driver's 4x goes on the same entry. |
| **Incident points** | When iRacing reports more incident points for a driver, they are attached to that driver's off/slowdown from the last 15 s, or logged as their own incident. |

Pressing **Replay** pauses playback, seeks the replay tape to the event's
session time minus a pre-roll (6 s by default), points the camera at the
driver and plays. It seeks by **session time**, not frame numbers or
iRacing's incident markers, so it lands on the right moment even after you
have been scrubbing around. **Go live** (or `L`) returns to the live feed.
Set `replay_auto_return_s` to return automatically.

Other replay buttons: **↺ 10s / 30s** (instant replay of whoever is on camera),
**◀ Inc / Inc ▶** (step through iRacing's own incident markers), pause/play.

Things to know:

- Replays need iRacing's replay buffer. Keep *Options → Replay → Write
  Replay Data* enabled, and give it enough memory to cover the race.
- Detection pauses while you are watching a replay (telemetry then shows the
  replay, not the live race), so moments that happen during a replay are
  not logged. iRacing's **◀ Inc / Inc ▶** markers still cover them.
- Incident **points** for other drivers only appear if iRacing shares them
  with you, for example as a league admin or in hosted sessions. Off-track and
  slowdown detection works regardless.
- Thresholds (`overtake_hold_s`, `slowdown_ratio`…) can be tuned in
  `config.json`.

## Grid walk

![grid walk: two cars in their grid boxes, seen at an angle from beside the track](docs/gridwalk-track.png)

The **Grid walk** tab runs a broadcast graphic that goes through the whole
field, front to back, two drivers at a time. The grid is seen in
perspective from high up beside the track, looking down across it at an
angle, the grid running gently downhill from left to right (the front of
the grid on the right), like a TV grid graphic: textured tarmac with the
racing line rubbered in, red and white kerbs, grass, and beyond them a wall
with advertising boards (the league's name), a catch fence and a grandstand.
The front car of the row stands in its painted grid box on the far lane,
further up the road, and the second one in the box staggered behind it, as
on a real grid. In front of each box its number is painted, with the car's
qualifying gap under it (pole: its lap time); pole has the start line ahead.
The cars either side on the grid stand in their boxes too (*Cars either side
on the grid*: show them, or hide them for just the pair, the last pair fading
as the camera moves on), and moving on to the next pair the camera glides
down the grid to it: the new pair's cars slide in along the road into their
boxes as the last pair's slide on out of the picture, and each card slides
in from its own side of the screen (the front car's from the right, the
second's from the left) and back out the same way. Each driver has a card
in the driver-on-camera card's style (top right for the front car, bottom
left for the second): the card opens from the middle with a light sweep,
and closes the same way as it goes. Its settings are the driver-on-camera
card's: grid position overall, in class or both (the class name with it or
not), class colour from the main or secondary class, car number, class
badge, team name, team logo (and its size), car badge; and **Qualifying**:
the gap to the class pole, the interval to the car ahead in class, the lap
time or nothing, also painted on the track under each box's number if you
like. **Car picture size** makes the cars bigger or smaller in their boxes.
With everything on, the card shows the driver's details: grid position (and class position in multiclass races), car
number in the class colour, class badge, car badge, name, nickname, team and
team logo, and their qualifying time (the class pole's lap, the gap to it
for everyone else). **Names** sets the name style (full name, A. Driver…)
and *Nickname under the name* can be turned off.

- **Car pictures**: you make them, the app puts them in the right place.
  Put them in one folder and point *Car pictures → Folder* at it. Name each
  picture **`iRacingID.Carname`**, e.g. `123456.Porsche 911 GT3 R (992).png`
  (PNG, JPG or WebP):
  - the **iRacing ID** is the driver's customer ID;
  - the **car name** is the car they're driving: iRacing's name for it
    (`Porsche 911 GT3 R (992)`), its short name (`Porsche 911 GT3 R`) or its
    folder name (`porsche992rgt3`) all work, in any case.
  Each driver in the session is matched by ID and the car they're in, so a
  driver with a picture for each of several cars gets the right one; a
  driver with only one picture gets it whatever the car. Pictures with a
  see-through background and the car pointing right look best (*Flip the
  car pictures* turns pictures of cars pointing left around). New or
  changed pictures in the folder show up by themselves. The grid list shows
  who has a picture, and what to call the missing ones (hover *No
  picture*). A driver without one gets the league's car photo if they have
  one, else a car drawn in their iRacing paint colours.
- **Order**: the grid comes from qualifying. If there are no qualifying
  results yet, the latest qualifying session's results are used, then current
  positions, then car number. Every driver entered in the session is included,
  even if they haven't loaded onto the track (flagged *Not on track*). Drivers
  without a qualifying time go to the back. Use **↑ / ↓** to fix the order by
  hand (inverted grids, penalties), and **Reset order** to go back.
  *League drivers not in session* adds the active league's remaining roster at
  the back.
- **Controls**: *Start from P1*, *Pause/Resume*, *Prev/Next* pair, *Show*
  on any driver to jump to their pair, and *Hide* to take it off screen.
  *Seconds per pair* sets the timer (used as soon as you type it, and kept
  for next time with Loop, Auto-play and the rest), and *Loop* restarts from the front.
  Without Loop, the graphic leaves the screen after the last pair.
  **Auto-play** (on by default) moves on to the next pair when its time is
  up; with it off, a pair stays until you press *Next* or *Prev* (or their
  hotkeys).

**On stream**: in OBS add a **Browser Source** of 1920×1080 pointing at
`http://localhost:8180/gridwalk.html`. It fills the screen. The walk runs on the server, so the
OBS source, the preview in the tab, and any other copy all stay in step. Add
`?preview=1` to the URL to view it on a backdrop in a normal browser.

## Stream overlays

Each overlay also has a **full-screen** version (`/standings.html?screen=1`,
`/laps.html?screen=1`): a complete screen with its own background, to cut to
on stream or put on a monitor (open it, then F11).
- **Standings board**: every driver. In a race it shows laps, gap,
  interval, last and best lap and pit stops. In qualifying it shows best lap,
  gap and interval. Big fields split into columns.
- **Live timing**: every driver in qualifying, with sector boxes coloured as
  they're set, the running lap clock, best lap and gap.

![full-screen standings board](docs/standings-screen.png)

The **Overlays** tab has each overlay's address for OBS, a **Preview ↗**
button and its settings. Add each one as a *Browser Source* at 1920×1080 (the
background is transparent). Settings changed in the tab show on stream
straight away and are kept in `data/overlays.json`. Each overlay's (and
board's) settings are in sections that open and close (What it shows,
Header, Columns, Drivers, Size & background…); settings that only matter
when another is on, like the fastest lap flash timer, appear once it's on.

- **Standings** (`/standings.html`): in a race, the running order with the gap
  to the leader. In qualifying and practice, it shows the fastest clean lap,
  and drivers only appear once they have one, so it starts empty.
  - **Race gaps** are the app's own, not iRacing's (which only refreshes now
    and then for other cars, so it lags and sticks): the track is split into
    timing points about every 10 m, and a car's gap is how long ago the car
    ahead was exactly where it is now, updated many times a second. The
    times are kept for the whole race, so a replay of any lap, during the
    race or after the flag, shows the gaps as they were.
  - *Overall* lists everyone. Each driver's class shows in the colour of
    their number and stripe.
  - *By class* gives each class its own block with its header and logo, or
    shows just one class.
  - **Header**: the session, with laps or time left. *Automatic* follows how
    the session is limited ("LAP 5 / 20", then "FINAL LAP" and
    "FINISHED"; or "12:34 LEFT", then "LAST LAP" once the clock has run out,
    until the chequered flag). You can also pick laps, time or nothing.
  - **Fill in as drivers complete a lap** (on by default): at the start of
    any session, only the header shows (session, and laps or time left). In a
    race, nobody shows before the green, and each driver appears once they've
    done a full lap, as they start lap 2, so the tower builds up in order at
    the end of lap 1. In qualifying, a driver with a lap done but no clean
    time yet is listed at the bottom.
  - **Green flag**: when a race goes green, the header (tower and full
    screen) flashes green five times with a light sweeping across it, then
    stops. Races only, and only if the overlay was open for the start.
  - **Chequered flag**: when the leader takes the chequered flag, the header
    (tower and full screen) turns into a black-and-white chequered flag. It
    flashes in a few times with a light sweep, then keeps waving until the
    session changes (e.g. to the next race) or the overlay is taken off
    screen. The header's text stays readable: the flag carries a dark tint
    over the whole header, the same size as the flag, and the text a shadow.
    Races only, and only if the app saw the finish.
  - **Finish flags**: in a race, as each driver crosses the line after the
    chequered flag, a small chequered flag comes out on a tab of its own on
    the tower's right edge, level with their row (sliding out from behind
    the tower), and keeps waving, every flag in time. On the full screen it's
    by their name. Rewinding a replay to
    before the finish takes them away again. *Chequered flag by each driver
    as they finish the race* turns them off.
  - **Columns** (each on or off):
    - gap to the leader (or to pole);
    - interval to the car ahead;
    - places gained or lost since the start;
    - best lap and last lap;
    - laps completed and pit stops;
    - a PIT badge on pit road.

    Small labels head the columns, and the tower widens to fit them.
  - Choose the name style, how many drivers, and whether to show car numbers,
    team names and team logos. The team logo and the team name are columns
    of their own, each turned on and off by itself: **Team logo column**
    before or after the driver / team name (the same size either way), and
    on the tower the **team name** under the driver's name or in a column of
    its own. The full-screen standings follow the same choices.
  - **Column headings** (the small GAP, INT… row) can be turned off.
  - **A background of its own for each column**: tick it, pick the column
    background colour and set each column's background opacity (position,
    car number, team logo, driver, team name, +/−, gap, interval…); the text
    stays as it is. On the tower the columns then make the panel. For the
    tower and the full-screen standings; the championship, teams',
    manufacturers' and results boards have the same option for their own
    columns.
  - **Column order**: drag the columns into the order you want (or use their
    arrows), separately for the tower and the full-screen standings. Columns
    that are switched off keep their place for when they're on. The full
    screen's usual order differs between races and qualifying until you
    change it.
  - **The leader's gap shows**: "Leader", or the lap they're on ("Lap 12").
    By class, each class leader shows their own lap.
  - **The leader's interval shows**: nothing (as before), "Leader", or the
    lap they're on ("Lap 12"); everyone else shows the gap to the car ahead.
    The full-screen version follows it too.
  - **Colours**: *Coloured bar by each driver*
    and *Car number background* can each be turned off. The background is in
    the driver's class colour; with it off, just the number shows. Both the
    tower and the full-screen version follow these.
  - **Class colours from**: the driver's **main** class or their
    **secondary** class (League builder), for the car number's background;
    **Coloured bar's colour from** sets the bar's on its own (the same class
    as the car number, the main or the secondary class, or the driver's
    **team colour**), so the number can show one class and the bar the
    other. The bar keeps that colour overall and by class alike; with the
    team colour, a driver whose team has no colour gets their class's. A driver without one (no main
    class in the league, say, only a secondary one) shows no colour: just
    the number, with no background, and no bar. With no league active, the
    iRacing class colours are used.
  - **Time left**: "12:34 LEFT", or just "12:34" with *"LEFT" after the
    time left* off.
  - **Accent colour**: the colour of the time or lap in the header, the bar
    down the left of the tower's header and the line under the full-screen
    header: orange, a colour of your own, or **by session** (white for
    practice, purple for qualifying, red for the race; each can be changed).
  - **Sponsor logo bar**: a small bar under the tower's header with a
    sponsor's logo. Pick which sponsors (several take turns, every few
    seconds as set) and how tall it is.
  - **Header**: the session name, laps or time left, and under them the
    series (the active league's name) and the track. *Series name* and
    *Track name* turn each of those on or off. *Race name*, *Qualifying
    name* and *Practice / warm-up name* replace RACE, QUALIFYING and
    iRacing's name for practice, e.g. "FEATURE RACE" or "SUPERPOLE"; leave
    one blank for the usual name. Both the tower and the full-screen version
    use these.
  - **Heat racing**: an event with heats, a consolation (last chance) race
    and a feature is recognised from iRacing's session names. *Heat race
    name*, *Consolation race name* and *Feature race name* replace iRacing's
    names for those (several heats keep their number: "Qualifying Heat 2").
    On the day of a heat event, each race takes the name of the league's
    round for it instead, exactly as it's named in the Championship tab: the
    rounds dated today (Championship → Calendar & results) go with the
    races in order. *Heat events: name each race as its round is named*
    turns this off. The live championship and the results saved after each
    race go to that round too. (Just after midnight, the day before still
    counts.)
  - *Wrap a long session name* puts a long name on two lines in the
    tower; off, it stays on one line and the tower widens for it (or ends in
    "…" if you've set the width).
  - **Width**: automatic (0, the default) or a width in pixels. In
    automatic mode each column, the name column included, is as wide as its
    widest entry plus a little room, and the tower is exactly as wide as
    that. It grows straight away when something needs more room, and only
    narrows once there's clearly room to spare, so it doesn't twitch as
    numbers change. With a width set, the name column takes what the other
    columns leave, and long names end in "…". **Driver name column width**
    sets the name column's width in px by itself (0: automatic), on an
    automatic or a set tower width; longer names end in "…".
  - **Extra drivers**: when there are more drivers than rows, a few more go
    under the top of the order, after a small "• • •" gap; in the By class
    view, under the top of each class, from that class. *Extra drivers show*:
    - **The rest of the field, a set at a time** (default): with 20 rows and
      3 extra, P21–23, then P24–26, and so on to the end, then back to
      P21–23. *Seconds per set* sets how long each set stays. Every copy
      of the overlay changes set at the same moment.
    - **The last ones**: always the last few, last place included.

    *Extra drivers' opacity* dims them (10–100%). 0 extra drivers turns it
    off. A set always fills every extra row: when the rest of the field
    doesn't divide evenly, the last set carries on from the top of it.
    **Max drivers** and **Extra drivers** are set separately for *Overall*
    and *By class*, and the tower uses the pair for the mode it's in.
  - **Close racing**: with the *Interval* column on, a driver within 0.15 s
    of the car ahead has their interval in red text. It stays red until they get
    past (then whoever is now right behind turns red, if close enough) or
    the gap opens up. It's racing under green only, not behind the safety
    car. Set the threshold, or 0 to turn it off.
  - **Transitions**: drivers slide up and down the tower as they change
    places, with a brief green (gained) or red (lost) glow. New drivers fade
    in. The stopwatch pops in when the fastest lap changes hands. The
    fastest-lap pill drops in saying "NEW FASTEST LAP", then switches to the
    driver and lap time, and fades out at the end.
  - **Fastest lap**: a purple stopwatch by the holder's name. In Overall it's
    the one fastest driver; in By class, each class's fastest.
  - **New fastest lap flash**: when someone sets a new fastest lap, a purple
    pill appears at the top middle of the screen with a stopwatch. It says
    "NEW FASTEST LAP" for about two seconds, then shows the driver and the lap
    time. Set how many seconds it stays (3 or more). It can also flash each
    class's new fastest lap. Races skip the first lap; laps set before the
    app connected don't flash.
- **Championship battle** (`/battle.html`): a few drivers fighting for the
  championship, in a small table in a corner (or along an edge). Pick the
  championship (Overall or any class, secondary classes too) and up to six
  drivers in its card on the Overlays tab, or in one go:
  - **The car on camera and the one ahead** (in that championship's running
    order on track; the leader on camera: it and the car behind);
  - **The car on camera and the cars either side**;
  - **The championship's top 3**.
  These put it on screen too, and can have hotkeys. It lists them in
  championship order with each one's place and points. During a race it
  works them out as if the race ended now ("If it ended now"): the points
  this race gives them (+18), places gained or lost in the championship
  (▲1), and the new totals. **Points gap**: to the first of them, or to the
  driver above. Car numbers (class colours), team logos and names, the
  heading, name format, place, size and background can be set. It shows
  once the championship has standings: after the first results, or live
  during a race.
- **Pit stops** (`/pits.html`): a card for a car in the pit lane, with two
  clocks:
  - **Pit lane**: from the moment it crosses the pit lane entry line to the
    exit line;
  - **In box**: the time it spends in its pit box (added up if it moves in
    and out), lit up while it's stopped; "—" for a drive-through.
  The tag says *PIT LANE*, *STOPPED* or *OUT*. **Show**: every car in the
  pit lane (the one on camera first) or only the car on camera, and **how
  many drivers at once** (the most cards on screen). **Each driver's card
  goes after** a number of seconds in the pit lane, if you set one (0: it
  stays until they leave); a card gone that way stays off until their next
  stop. **Card stays after they cross the pit exit line**: how many seconds
  it keeps the final times (0: it goes at once). Races only,
  unless you untick it. Position, car number (in its class colour), name,
  team name and logo can each be turned off. The position follows the
  standings tower: overall in *Overall*, in class in *By class*.
  - Cards open downwards from the top with a light sweep, the details
    following one after another, and close back up as they go; the
    championship battle comes in and goes out the same way. The clocks are the sim's own,
  so they're right in replays too (paused with the replay).
- **Driver on camera** (`/driver.html`): a small board at the bottom centre
  naming the driver the camera is on. **Position shown**: overall, in class,
  or both (overall, with the class position under it). *Class name with the
  class position* can be turned off, for just "P1" under the overall place. Then the car number
  in the class colour, name, class, team and logo, and car badge. *Class colour from*: the
  main or the secondary class, as for the standings; a driver without one
  gets no colour: no background behind the position or number, white text.
  - When the camera moves to someone else, the old board slides away and the
    new one slides up, opening from the middle with a light sweep.
  - **Card stays on screen for**: how many seconds it stays up (1 to 120).
    The time starts again with each new driver: switch to someone else
    before it runs out and their card replaces the last one for the full
    time. Picking the same driver again in the app (Timing tab) shows their
    card again. It keeps time by itself, so it goes on time even with
    iRacing paused.
  - **Stay up for as long as they're on camera**: no timer; it changes when
    the camera does.
  - **Team logo and car badge**: the team name is always under the driver's
    name. Next to it goes the team logo, with the car badge at the end of
    the card; or swapped: the car badge next to the team name and the team
    logo at the end. **By the team name**: the logo (or badge) before or
    after the team name.
  - Choose the details shown, the name style and the panel background. It
    only shows when the camera is on a driver, not on scenic cameras.
- **Sponsors** (`/sponsors.html`): the active league's sponsor logos (added
  in the League builder) over the race. Choose a corner or the middle of an
  edge, all together or one at a time (and how long each shows), the size,
  a caption such as "Partners", a dark panel behind, and which sponsors.
- **Lap tracker** (`/laps.html`): only in qualifying (practice too, if you
  tick it).
  - The car on camera gets the big tracker. Up to 12 small ones show other
    cars on a timed lap, nearest the line first.
  - Each sector bar fills as the car goes round and turns solid when the
    sector is done:
    - **purple**: faster than the reference;
    - **green**: within 0.2 s of it (adjustable);
    - **yellow**: slower.
  - The track's timing split points are merged into 3 sectors by default,
    like TV. The *Sectors* setting offers 2, 3, 4, or every split point the
    track has. The time sits inside each finished sector; with many sectors
    the small trackers show just the colours.
  - The reference is the driver's own best ("personal"), the fastest in
    their class this session ("session"), or the fastest of anyone this
    session, whatever their class ("overall"). Against the class or overall
    best, the colours keep up: a purple sector turns green once someone
    else goes faster through it, and a sector only counts as the fastest
    while its lap is clean: a lap that's invalidated (off track) loses its
    sectors from the bests, and whoever's now fastest (on a clean lap)
    turns purple.
  - **A sector just done** shows first how it compares (−0.324 faster,
    +0.512 slower) with the time it's measured against: the driver's best,
    the class's fastest or anyone's, as the reference above says. It fades
    in and out on the sector's colour for 3 seconds (a purple one with a
    white light sweeping across it, a green one with a soft pulsing
    lighter-green glow, a yellow one as it is), then the sector's time
    comes in (*A sector just done: its difference first, for*: the seconds,
    or 0 for just the time). The full-screen timing does the same.
  - **An invalidated lap** (off track): the sector it happened in gets a
    line through it, and the rest of the lap greys out as the driver carries
    on; at the line every sector is struck through and **INVALID** takes the
    lap time's place (the full-screen timing too). The colour of INVALID,
    of the invalidated sectors and of the line through them can each be set
    in the lap tracker's settings.
  - The driver's best lap is always shown. When a lap is done, its time
    stays up with the gap to that best (green if faster, red if slower), then
    the tracker goes after 5 s (adjustable). As the time comes in it pops
    up: a purple glow with a light sweeping across for the fastest lap (by
    the same reference as the sectors), a green glow for the driver's
    personal best.
  - Trackers open out from the middle with a light sweep and close the same
    way; the small ones slide to their new places as the order changes.
  - Laps aren't timed out of the pits. A lap is marked invalid if the car goes
    off track or into the pits, and invalid laps never count as bests.
  - Sector splits come from iRacing's sector points for the track. Lap times
    use iRacing's own time when it reports one.

![standings tower by class](docs/standings.png)

![qualifying lap tracker: big tracker for the car on camera, small ones for the rest](docs/laps.png)

## Team builder

The **Teams** tab works on the same league as the League builder. For each
team, set:
- its name (renaming moves its drivers with it);
- a short name, used where space is tight;
- a colour (optional; the class colour is used otherwise);
- its logo.

Add drivers to a team from the drop-down, or take them out with ✕. The roster's
*Team* column in the League builder is the same thing. **Save** saves the
league. The roster also has a **Driver #** column, for leagues that give
drivers their own number; the lap tracker can show it.

**Teams in more than one league.** Under each team, **Also in** lists your
other leagues: tick the ones the team races in too, then **Save**. The team
(name, short name, colour and logo) is copied into those leagues, and its
drivers who are in them too (the same iRacing customer ID, or the same name
for drivers without one) are put in it there. From then on:
- changes to the team in any of its leagues reach the others when saved;
- a driver who joins one of those leagues later, without a team, is put in
  their team by themselves;
- moving a driver to another shared team moves them in the other leagues
  too. Taking a driver out of a team only changes the league you're in.

Links are between two leagues: sharing a team from one league to another
doesn't link it with every league the other one shares teams with.
Unticking a league stops the link; that league keeps its copy of the team.
**✕** on a ticked league takes the team out of that league altogether: its
copy there is deleted and its drivers there are left without a team (the
league you're in keeps it).
Teams are matched by name, so a renamed team starts a new team in the other
leagues (the old one stays there until you delete it).

## Import & export

Everything you set up can be saved to a file: a backup, to move to another
PC, or to send to someone. Each kind is exported and imported where it's
made.

| What | Where | Export | Import |
| --- | --- | --- | --- |
| A whole league (classes, teams, drivers, championship, logos, banners, sponsors, photos) | League builder | **Export league** (.json) | **Import league…** (left side): added as a new league, never over one you have |
| Driver roster | League builder | **Roster (CSV)** | **Import roster (this app's CSV)…**: drivers matched by customer ID (else name) are updated, new ones added |
| Drivers, teams and classes from any spreadsheet (a sign-up sheet) | — | — | **Import a sign-up sheet (CSV)…** (League builder → Drivers, or Teams): see below |
| Teams (names, short names, colours, logos, who drives for whom) | Teams | **Export teams** (.json) | **Import teams…**: teams with the same name are replaced, drivers join their team |
| Championship (points rules, calendar, every round's results, penalties) | Championship | **Export championship** (.json) | **Import championship…**: replaces this league's championship |
| Championship standings (every table, round by round) | Championship | **Standings (CSV)** | |
| One round's results | Championship → Calendar & results → open a round | **Export** (.json) or **CSV** | **Import…**: from iRacing's own event result export (the .csv from the session's results page), a round export, or a CSV with the same columns; replaces that round's results |
| Every overlay's and board's settings, with background images | Overlays | **Export settings** (.json) | **Import settings…**: replaces your settings |

**Where exports go:** `Documents\Apex Commentator\Exports` on the PC the
app runs on. Files are named after the league, what's in them and the date,
e.g. `Sunday Cup - Teams - 2026-10-31.json`, and never overwrite each other.
After each export the app shows the file's name and full path, with **Show
in folder** (opens File Explorer with it selected) and **Copy path**. The Home
tab's *Import & export* panel has **Open exports folder**.

**.json** files are for importing back into Apex Commentator (they carry their
images inside them). **.csv** files open in Excel or Google Sheets; round
results and the roster can be edited there and imported back. Classes are
matched by name, so a league with the same class names picks results up
directly.

## Size

Every overlay and board has a **Size** slider (50–200%, 100% as designed):
- **Overlays tab:** standings, lap tracker, driver on camera and sponsors.
- **Boards tab:** each board.
- **Grid walk tab:** the grid walk.

An overlay grows or shrinks from where it sits:
- **Standings tower:** from its top-left corner.
- **Lap trackers:** from the bottom.
- **Sponsors:** from their corner or edge.
- **Driver board:** from the bottom centre.

Boards, the grid walk and the full-screen versions grow or shrink around the
middle of the screen. Changes show straight away, in OBS and on screen.

**Moving an overlay.** Every overlay (standings tower, lap trackers, driver
on camera, sponsors, championship battle and the grid walk) has *Move right*
and *Move down* under *Size, position & background*: how far to move it from
where it sits, in pixels of the 1920×1080 screen (minus moves it left or up).
Use it to keep overlays clear of each other, or of your own stream layout.
The full-screen versions and boards don't move.

## Backgrounds

Every overlay and board has a background setting:
- **Overlays tab:** standings, lap tracker and sponsors.
- **Boards tab:** each board, under *What each board shows*.
- **Grid walk tab:** the grid walk.

The choices:
- **Default**: the normal dark panels on overlays, and the boards' own
  backdrop.
- **Solid colour**: pick any colour.
- **Custom image**: upload a picture (PNG, JPG, WebP or SVG, up to 8 MB) or
  pick one uploaded before.

Colour and image both have an **Opacity** slider (0–100%).

What it colours depends on what it is:
- **On an overlay** (the standings tower, lap trackers, sponsors panel, the
  grid walk's title and driver panels), the setting is the overlay's own panels: their background
  takes the colour, or shows the image inside them, behind the text. The
  rest of the screen stays see-through, so the race is never covered.
- **On a board**, it's the whole screen behind the board: an image shows at
  its own size and shape filling the 1920×1080 screen (centred, cropped if
  it isn't 16:9), whatever the board's *Size*.
- **On a full-screen version** (full-screen standings or lap tracker), which
  is a whole screen, it's that screen's backdrop.

Uploaded backgrounds are kept with the app's data and can be used by any
overlay or board.

On your own screen (*Show on my screen*), the background only fills the
overlay's own panels, like everywhere else; the rest of the screen is never
touched.

**iRacing's event result export** (the .csv downloaded from a session's
results page, starting with the event's start time and track) imports into a
round as it is: finishing positions, starting positions, laps, laps led,
fastest laps, incidents, the gap to the winner (or laps down), and DNF / DNS
(a car out with no laps done is a DNS) from iRacing's "Out" column. Drivers
are matched to the roster by customer ID, and each gets their class in the
league (their own pick, name tag or iRacing car class). A driver with no
class (a safety car, say) is left out, as for results saved from the sim. A
round without a track or date gets the event's.

**Picking colours.** Next to every colour box is an **eyedropper**: click
it, then click anywhere on your screen (the game, a logo, a photo) to take
that colour; Esc cancels. In a browser it uses the browser's own eyedropper.
**Team logo size** (in each overlay's and board's *Size* section) makes the
team logos bigger or smaller, 40–250% (the tower's logo column grows with
them).

## Officials mode (official and AI races)

The top bar's switch, **League | Officials**, says what the overlays and
boards use. *League*: the active league (its names, classes, colours, teams
and rules, like leaving drivers without a class off). *Officials*: iRacing's
own data only, as if no league were active, for spectating an official or
AI race, so a league's settings don't get in the way. The league stays
picked: switch back and it's all there. In Officials mode the boards that
come from the iRacing event still work (a session's finishing order,
qualifying results, the starting grid, by iRacing's classes); championship
boards need the league. Activating a league switches back to League.

## Overlays on your own screen (no OBS)

Every overlay and board can also go straight on your monitor instead of into
OBS or a browser. In the app window, press **Show on my screen** under its
link: the Overlays tab for the standings tower, lap tracker (and their full
screen versions) and sponsors, the Boards tab for boards, and the Grid walk tab.

- It sits over whatever is on that monitor, always on top. Run iRacing in
  **windowed or borderless** mode: a game in exclusive full screen covers it.
- Only the overlay itself is on screen: its window is cut down to where the
  overlay draws (the tower, the fastest lap pill, the driver board…) and
  follows it as it grows, shrinks or slides. The rest of the screen isn't
  covered at all. Full-screen versions and boards are a whole screen.
- It never takes the keyboard, and your mouse goes straight through to the
  game or the app underneath.
- With more than one monitor, pick which one once, at the top of the
  Overlays tab (for every overlay and the grid walk) or the Boards tab. The
  app remembers it (the "everything on my screen" hotkeys use it too);
  changing it moves anything from that tab already up.
- **Remove** takes it down; *Remove all from my screen* clears everything.
  They also close with the app. **Show all on my screen** (Overlays tab) puts
  every overlay up at once: the standings tower, lap tracker, driver on
  camera, sponsors, championship battle and pit stops (each still shows only
  when it's turned on). Hotkeys can do the same: every overlay, the boards,
  or remove everything.
- The first time (and the first time after each update), the app asks
  whether you can see your screen through it.
  If you don't answer within 15 seconds it takes the overlay down by itself
  (in case it came up solid and covered your screen). From then on it just
  appears.
- The app notes each on-screen overlay it puts up, and anything that went
  wrong, in its log: `apex.log` in `%APPDATA%\Apex Commentator` (paste that
  into the Windows + R box).

This needs the app window (it isn't available when the app runs in a browser).
Soft drop shadows are left out on screen, since only fully see-through parts
can show the game behind.

## Boards (full-screen championship, calendar and results)

The **Boards** tab puts a full-screen board on stream with one click. Add
`/board.html` to OBS as a *Browser Source* at 1920×1080. It's empty
(transparent) until you put a board on screen, and **Take off screen** clears
it. **⧉ Pop out** opens the Boards tab in a window of its own. The buttons are
built from the active league:

- **Championship standings**: Overall, and one button per class (e.g. PRO,
  SEMI-PRO, AM): that championship's drivers with their points, the gap to
  the leader and, if switched on, the gap to the driver ahead.
- **Teams' championship**: each team's logo and colour, the drivers who
  scored for it, points per round, wins, penalties, and the gaps to the
  leader and to the team ahead.
- **Manufacturers**: by the cars' makes, Overall and per class.
- **Season calendar**: every round with track, layout, date, time and
  length, which rounds are done (with their winners) and which is next.
  - **Round titles**: "Round 3 · your round name", just your round name, or
    just "Round 3". A round you haven't named is always "Round 3". A round's
    race length is a number of minutes, hours or laps (Championship →
    Calendar & results).
  - The top of each card: the round's number and its own name ("Round 3 ·
    Spa Showdown"), or for a race meeting of several races (heat races, say)
    "Rounds 4–6 · Fuji Night".
  - Each race has a box: its name and length (Sprint 20 min), and once it's
    run, each class's winner under it, one a line (Gold: A. Konig, Silver:
    M. Frederik…). A race meeting has a box for each race, side by side.
    *Each race's name in its box*, *The class name by each winner* and the
    winners' name style can be set. **Winners shown** has a tick box for
    Overall and each class: only the ticked ones' winners show.
  - **Dates as**: Sun 22 Nov, 22/11/26, 22nd November, 22nd November 2026 or
    Sunday 22nd November.
  - A round with a points multiplier other than 1 (Championship → Calendar
    & results → *Points ×*, e.g. 2 for double points) shows "×2 points". This
    can be turned off. Or
  the league's own calendar image instead (see *League builder*).
- **Finishing order**: Overall or for any class of the league (secondary
  classes too, and classes without points of their own, which show their
  drivers in order without points), from the latest round, a chosen
  round, the session going on now (live), or any session of the event in
  iRacing (practice, qualifying, warm-up, each heat, the race) once it has
  results. Races show their finishing order with the points; practice and
  qualifying show the order by best lap, without points (drivers with no
  time aren't listed).
- **Qualifying results**: a qualifying session of the iRacing event (the
  latest one, or any you pick), Overall or a class: by best lap, with the
  gap to pole (the class's pole in a class) and the interval to the car
  ahead, and laps if you like.
- **Starting grid**: the grid for a race of the event (the race on now, else
  the next one; or any race you pick), worked out from the session before
  anyone has loaded in, Overall or a class. *The grid from*: qualifying, the
  previous race's finish, or the grid walk's order (fix it by hand on the
  Grid walk tab). **Reverse grid**: the first N turned round (0 = none),
  overall or the first N of each class: e.g. a final race with the top 8
  reversed. *Layout*: a list, or as the cars line up (two staggered
  columns). It can show the place in class, car numbers, team names and
  logos, car badges, the qualifying lap and gap, and where they finished
  the previous race. Pick the race on the Boards tab; the grid rule is in
  its settings, so change it before the race it's for. *Show the drivers*:
  all at once (each driver comes in in turn), or **row by row**: the front
  row first, then *Next row* (on the Boards tab, or a hotkey) brings in each
  row after it, sliding into place (*◀ Row* takes one back, *Show all* the
  rest); the board's page follows the rows. Every board comes in and goes
  out with its own animation; the qualifying results wipe in a driver at a
  time from pole, each lap time catching the light.

Under *What each board shows*, every board can be set up separately:
- the league logo in its header;
- a league banner across the top or bottom or down either side, and which
  banner;
- the league's sponsor logos along any edge, and which sponsors;
- the board's own columns: car numbers, team names and logos, car badges,
  gaps, wins, penalty points, points from the last few rounds, laps, places
  gained, fastest lap (purple), points scored;
- the finishing order's **Gap** (to the winner, or the class winner) and
  **Int** (to the car ahead): seconds, or "+1 Lap" for a car a lap down. A
  DNF, DNS or DSQ shows there instead of a time. Gaps come from iRacing's
  race times once the race is over, and live timing while it's on; practice
  and qualifying show the gaps between best laps;
- how many drivers (or teams, manufacturers, race meetings) a page.
- **Names**: the drivers' name style (full name, T. Smith, Smith T., last
  name, first name, 3 letters, nickname) on the championship, teams' and
  finishing order boards; the calendar has its own for its winners.
- the board's look: **gold, silver and bronze** for places 1–3 (else the
  accent colour), an **accent colour** of its own (the line under the
  header, the page number…), which you can also pick from the main colours
  of the board's background image, and whether the **league name** shows in
  the header;
- **the leader at the top of every page**: page 2 starts with the leader,
  then carries on from where page 1 stopped;
- the finishing order's **winner's Gap**: their laps (13 Laps), their race
  time (from iRacing's results, or the average lap × laps of an imported
  iRacing results file), or nothing.

**Pages.** A board with more than that runs onto further pages: **Next ▶**
and **◀ Prev** by *Take off screen* go through them (positions carry on, so
page 2 starts at P11 with 10 a page), and "Page 2 of 3" shows where you are.
The board shows "2 / 3" in its header (this can be turned off). Each new
board starts on page 1. *Next page* and *Previous page* can have hotkeys too.

Putting another board on screen crossfades from the old one, and a new
board's header and rows sweep in one after another; **Take off screen**
fades it out. Long tables split into two columns rather than shrinking. Names follow the
league's *Remove driver class in name* setting, and car numbers take the
class colour.

## Championship

The **Championship** tab keeps each league's season. It works on the same
league as the League builder and Teams tabs. Press **Save** after changes; the
standings update from what's saved.

- **Points & rules**
  - Points for each finishing position (e.g. `25, 18, 15, 12, 10, 8, 6, 4,
    2, 1`).
  - Optional points for qualifying positions, taken from the starting grid.
  - **Championships**: tick **Class championships**, **Overall
    championship**, or both. Each has its own points table: *Class points*
    for class finishing positions, *Overall points* for overall finishing
    positions, so two scoring systems run at the same time:
    - *Class only*: scored on class positions; each class is its own
      championship.
    - *Overall only*: scored on overall positions with the overall points;
      one championship for everyone.
    - *Both, as two separate championships*: every result scores twice and
      the points are kept apart. Class positions score class points in the
      class championship, and overall positions score overall points in the
      Overall championship. Bonuses and penalty points apply in both, and
      each standings table shows what it's scored on.
      Example (class points 10, 6, 4; overall 20, 15, 10, 5): a PRO driver
      who finishes 3rd overall and 2nd in PRO scores 10 towards Overall and
      6 towards PRO.
    - *Both, added together*: every result scores once, as its class
      position's class points plus its overall position's overall points.
      Bonuses count once. Each class's table and the
      overall table rank the same totals. Same example: the PRO driver
      scores 6 + 10 = 16, in both PRO and Overall.
    - *Overall points count as class points*: every result scores the
      overall points for its overall position, and the same points go into
      the driver's class championship: each class's table ranks its
      drivers on their overall points. Same example: the PRO driver scores
      10 towards Overall and 10 towards PRO.
  - **Different points for a class**: any class (a secondary one too) can
    have its own points table; leave it empty for the usual one.
  - **Secondary classes** (set up in the League builder) always have their
    own championship, whichever option above is picked, so a driver in two
    classes scores in both (and overall), each on its own points. Under
    *Secondary classes* choose how each one scores:
    - *On where its drivers finish among each other* (the default), on the
      class's own points table (or the class points);
    - *The points its drivers score in their own class*;
    - *The points its drivers score overall*.

    The round results show what each driver scored in every championship
    they're in ("Overall 20 · Pro 10 · Rookie Cup 10"). Ranked among each
    other, with a Rookie Cup of drivers who finish 4th, 9th and 12th
    overall, the 4th-placed one wins the Rookie Cup. Their main class and
    overall points don't change.
  - **Drop rounds**: each driver's worst N rounds don't count. Missed rounds
    are dropped first. Drops only start once a driver has more rounds than N.
  - **A race meeting drops as a whole**: a meeting's races (heats, a sprint
    and a feature…) count as one for the drop rounds, their points added up,
    and drop together.
  - **Custom points system**: tick it to give different kinds of race their
    own points (a sprint, a feature…). Add as many points systems as you
    like, each with a name, its points (1st, 2nd, 3rd…) and, with an overall
    championship, its own overall points (empty: the same). Then pick one for
    each round under *Calendar & results* (*Points*); a round left on *Usual
    points* uses the class and overall points above.
  - The fastest-lap bonus can be limited to the top N finishers.
  - **Race distance to score** (75% by default): a driver must complete this
    share of their class winner's laps. Anyone short is a DNF and scores no
    points or bonuses. 0 turns it off.
  - Whether DNFs score for where they're classified.
  - **Team championship**: count every driver, or each team's best N per
    round. With *Both*, teams count their drivers' overall points, or class
    points if you choose. Secondary classes never count for teams.
  - **Bonus points**: pole, fastest lap, led a lap, each lap led, most laps
    led, most places gained, clean race (no incidents), finished, started, and
    race win. Use 0 for bonuses you don't award; negative values take points
    off.
- **Rounds & results**
  - Add the season's rounds, with a points multiplier (2 for double points)
    and *Can't drop* for rounds that always count.
  - **Build the rounds from a calendar** makes the whole season at once, from:
    - **a scan of the league's calendar graphic**: the calendar image from the
      League builder, or any image you choose. The app reads its text (with
      Windows' own text recognition, so nothing to install) and finds each
      round's track and layout, date, start time and length. It copes with
      tables (a round per row), lists and grids of cards. Tracks it doesn't
      know are marked to check.
    - **pasted text**: the calendar copied from Discord or a website, a round
      a line or in blocks ("Round 1 - Spa - Sun 8th Nov - 8PM - 60 min").
      Dates like 22/11/26 are read day first, or month first on a US PC (a
      date that can only be one way round settles it).

    Every round found is listed to check and correct (or leave out) before
    any are made, and they can be added after the existing rounds or replace
    the rounds that have no results yet.
  - **Race meetings**: for leagues that run several races in one event (three
    heat races, say) and count each race as a round. Each race is a round of
    its own for the points; the meeting groups them. Make them with *Races at
    each* when building from a calendar (each entry becomes a meeting of that
    many races, called Race or Heat 1, 2…), or with **+ Add race meeting**.
    Rounds already made can be changed on the fly: **⇉ Race meeting** on a
    round makes it the first race of a meeting (its results stay with that
    race) and adds the others after it, at the same track, date and time;
    **Make every round a race meeting…** does that for every round at once.
    **Separate rounds** on a meeting turns its races back into rounds.
    **Import every race from session** fills a meeting's races from the race
    sessions of the event you're in, in order (heat 1 into the first race,
    and so on), including races that already finished: those come from
    iRacing's results, so their statuses and starting places are worth a
    check. During the event, the live standings count the race in progress
    as the first race without results.
  - **Results save themselves** (ticked by default, at the top of
    *Calendar & results*): when a race is over (cool-down, or every car that
    started has taken the flag or left the track), its finishing order goes
    into the round it counts as: the one marked *Live*, else the first round
    without results, or a new round if there's none. Statuses (finished,
    DNF, DNS, DSQ) and points are worked out as for an import, so the
    championship standings and boards are up to date for after the race. If
    the session moves on, or iRacing is closed, before that, the race is
    saved as it last stood. A race already imported isn't touched, and the
    app says when it has saved one. Heat races go into a meeting's races one
    after another.
  - Or, after a race, press **Import from session** while still in the session.
    This fills in finishing order, class, grid, laps, laps led, fastest lap
    and incidents from iRacing, and adds drivers missing from the roster.
  - Each driver's status comes from the app watching the race:
    - **Finished**: crossed the line after the chequered flag.
    - **DNF**: started but didn't take the flag (retired, or parked in the
      pits), or fell short of the race distance.
    - **DNS**: never joined the track once the race went green.
  - If the app wasn't running for the whole race, it falls back to iRacing's
    results, which can't tell a car parked in the pits from a finisher.
    Check those statuses by hand.
  - Everything can be corrected by hand, including DSQ and extra points
    (+ or −) for a round. The points column shows what each result scored.
- **Penalties**
  - *Points off* are taken from the driver's total (and their team's) and are
    never dropped.
  - *Licence points* are a running tally per driver, shown in the standings.
- **Standings**
  - One table per class with each round's points. Dropped rounds are struck
    through, and hovering a cell shows its bonuses.
  - Ties are broken by most wins, then most seconds, and so on.
  - Below the drivers is the team championship.
- **Live**
  - During a race with the league active, the standings tab shows the
    championship as if the race finished now: race points, points before,
    live total, gap, and places gained or lost.
  - The race counts as the round marked *Live* (by default, the first round
    without results).
  - The same data is in the app's live feed (`championship` in
    `/api/state`), ready for a points-battle overlay.

## League builder

Open the **League builder** tab.

1. **Build from the current session**: takes the drivers in the iRacing
   session you're in (names, customer IDs, car numbers, teams).
2. **Blank league**: type it in by hand.
3. **Import league…**: a league exported from Apex Commentator, on this PC
   or another.

No iRacing login is needed for any of it.

The league's settings are on three tabs: **Drivers** (the roster),
**Classes**, and **Logos, banners & sponsors**. *Teams ↗* and *Season &
points ↗* jump to the team builder and the championship.

**Arrow keys** move between the boxes in the Drivers list, the classes and
the team cards: up and down to the same box in the row (or card) above or
below, left and right along the row. As in a spreadsheet, a box's text is
selected when you arrive, so left and right go straight on; once you click
in it or type, they move through the text first.

**Drivers with no class**: in a league with classes, a driver with neither
a main nor a secondary class (a safety car, say) is left off every overlay
(standings, lap tracker, driver on camera, grid walk) and out of the
results, so they're on no board either. The Timing tab still lists them,
tagged *NO CLASS*. Untick *Drivers with no class … on no overlay* under
**Classes** to show everyone.

**Import a sign-up sheet (CSV)…** (Drivers tab, or the Teams tab) reads any
spreadsheet saved as CSV, e.g. a league's sign-up sheet. It works out which
column is which (iRacing customer ID, full name or first and last name, car
number, team, team colour, class, nickname) and shows its guess to check or
change: the class column is found by its heading, or without one by its
values (a column of a few repeated words such as GOLD / SILVER / BRONZE).
Pick whether the classes are **main** classes (shown on the overlays) or
**secondary** ones. Then **Import**: drivers already in the league (same
iRacing ID, else the same name) get the sheet's details, everyone else is
added, and any team or class the league doesn't have is made (Gold, Silver,
Bronze get their usual colours). Car numbers keep their leading zeros
("021"). The league is saved.

**⧉** by a saved league duplicates it: drivers, classes, teams,
championship and images, as "<name> (copy)", to rename and change (a new
season, say). Under *Logos, banners & sponsors*, **◀ ▶** on a sponsor change
the order they're shown in everywhere (boards, the sponsors overlay, the
tower's sponsor bar); save to keep it.

Edit nicknames, teams and notes (for example "Championship leader" or a
pronunciation hint), **Save**, then **Use in overlay**. Drivers are matched by
iRacing customer ID, or by car number for hand-added entries without one.
**Add drivers from session** adds anyone new from the session you're in and
fills in blanks, keeping your edits. Profiles are plain JSON in
`data/leagues/`.

**Car**: each driver's car make (Porsche, BMW, Mercedes-AMG…), with its
badge, for the manufacturers' championship and the boards. Badges show
without any box behind them, in light versions where the maker's own is
black or navy, so they read on the dark panels.

**Team logos** never show in a white box: wherever a team logo appears (the
overlays, boards, grid walk and the app), a white or near-white background
around it is made see-through, and a logo that was dark on white is shown
light. Logos that are already see-through, or a coloured badge, show as they
are. *Auto* uses the
car they drive in iRacing, worked out from its name. Importing drivers from a
session fills it in, and each championship result keeps the car driven that
round.

**Sorting the drivers**: click a column heading in the driver list (Driver,
Cust ID, Car #, Driver #, Nickname, Team, Notes, Class, 2nd class, Car) to sort by it, A
to Z. Click again for Z to A, and a third time for the order they were added.
Numbers sort as numbers (2 before 10) and blanks go last. Only the list on
screen is sorted; the app remembers your choice.

**League logo, banners and calendar image** (for the boards):
- **League logo**: shown in the board headers.
- **League banners**: wide ones for across the top or bottom, tall ones for
  the sides.
- **Calendar image**: a calendar graphic the league has made itself, which
  the calendar board can show instead of its own. The rounds you enter still
  drive the standings, results and next-round information.

**Season calendar**: in Championship → *Calendar & results*, each round has
a track and a **configuration** picked from lists, plus date, start time and
length (e.g. "60 min").
- Type to search the track list; the configuration list then shows that
  track's layouts.
- The list is a built-in one of iRacing's tracks and main layouts, plus
  every track the app has seen in a session. A track not in the list can be
  typed in.

**Hide the class tag in front of names**: some leagues put the class in front of
driver names, like `(P) Dave Price` or `(PA) Mat Gatter`. Tick this box
(on the Classes tab) and:
- Every driver with a tag like that gets the name without it, minus the
  space, as their **Nickname** (`Dave Price`). Nicknames you've already typed
  are kept. Drivers added later (from the session) get one when
  the league is saved.
- The overlays (standings, lap tracker, grid walk, full-screen boards) show
  that nickname as the driver's name, so the name styles work properly
  ("D. Price", "Price D.").
- The grid walk (on stream and its list in the app) uses it too.
- The timing screen and roster keep the full `(P) Dave Price`, so you can spot
  a driver changing class.

**Classes from name tags**: a tag like `(P)` also puts the driver in the
matching league class, so their number and stripe take that class's colour.
The match is the class's name or an entry in its *iRacing classes* field
(e.g. `P`), or else the initials of its name: `P` is Pro, `SP` is Semi-Pro,
`PA` is Pro-Am, `AM` is Am, `G` is Gold, `S` is Silver and `B` is Bronze. The tag in the driver's current iRacing name
counts, so a class change shows as soon as the tag changes. A class picked
for a driver in the roster still wins.

### Classes and logos

![class editor](docs/class-editor.png)

Each class has a **name**, a **colour**, and optionally a **logo**.
**Build from the current session** creates one class per iRacing car class,
in iRacing's colours. Rename and recolour them as you like, or add your own
(for example Pro and Am within the same car).

A driver's class comes from:

1. the **Class** picked for them in the roster, or otherwise
2. the first class whose **iRacing classes** list contains their car class
   (e.g. `GT3`), or otherwise
3. their iRacing car class as-is.

**Main and secondary classes.** Each class is one or the other (its
**Kind**):
- **Main class** (the usual kind): what the overlays, timing screen and grid
  walk show. A driver is in one, found as above (*Auto (by car)* in the
  roster's **Class** column), unless you pick **—** there: no main class,
  whatever their car or name tag says. A driver with — and a secondary class
  shows on the overlays without a class name or colour from a main class; with
  neither, they're left off, as below.
- **Secondary class**: works in the background, e.g. a Rookie Cup or a
  Pro-Am trophy that runs across the main classes. Pick a driver's in the
  roster's **2nd class** column (it appears once the league has a secondary
  class). The driver keeps their main class everywhere on screen, and also
  scores in the secondary class's own championship, which has its own
  standings, results and board. Secondary classes are never picked by car
  class or name tag. Switching a class's Kind moves the drivers picked for
  it to the other column.

On the **Timing** screen, each driver's class position is underlined and
their car number edged in the class colour, and the class chips above the
standings show one class at a time. Class logos show by the drivers in the grid walk.

**Built-in logos.** The league's tier logos ship with the app as layered
SVGs in `web/logos/`: PRO, SEMI-PRO, PRO-AM, AM, GOLD, SILVER and BRONZE.
Pick one from a class's **Logo** list. A class named after one of them
("Pro", "Semi Pro", "Gold"…) picks it up automatically. The badge is drawn
in exactly the class colour. The lettering stays white unless white would be
hard to read on that colour (under 3:1 contrast), when it turns dark: Gold
and Silver, for example.

**Logo backgrounds.** You can also upload your own PNG, JPG, WebP or SVG (up
to 8 MB) per class. For SVGs with marked layers, the overlay recolours those
layers exactly (see *Adding logos* below). For any other image it replaces
the logo's background with the class colour, so the logo blends into the
header, and the result updates live as you change the colour:

- **Auto-detect** reads the background from the logo's border: transparent,
  or its most common colour (white, black…). The detected colour is shown
  under the class.
- **Pick logo background** names the colour to replace, for logos where
  auto-detect guesses wrong.
- **Keep logo as is** turns recolouring off.
- **Tolerance** sets how close to the background a pixel must be to get
  recoloured. Raise it for JPEG noise; lower it if parts of the logo get
  eaten.
- **Enclosed areas too** also recolours background-coloured areas that don't
  touch the edge, like the inside of an "O". It's off by default because it
  would also recolour white artwork inside the logo.

By default only the background connected to the logo's edge is replaced,
with anti-aliased edges blended into the new colour. Your original file is kept
untouched, in `data/leagues/logos/<league>/`.

**Adding logos.** `tools/logo_to_svg.py` turns a dark-badge, light-lettering
logo (like the built-in ones) into a layered SVG. Straight badge edges are
fitted as exact lines, and the lettering is traced with Potrace.

```
pip install pillow potracer          # only needed for the converter
python tools/logo_to_svg.py my-logo.png --out-dir web/logos
```

Drop the result in `web/logos/` to add it to the library, or upload it to a
class. In a hand-made SVG, mark the part that should take the class colour
with `data-apex-fill="class"`, and the lettering with `data-apex-fill="ink"`.

## Updates

On start-up, and every few hours after, the app checks this repository's
GitHub releases. The **Updates** panel on the Home page shows:
- your version and the newest one;
- when it last checked, and anything that went wrong;
- **Check now**, **Install update** and **Release page** buttons.

When a newer version is out, the control panel also pops up with its release
notes:

- **Update now** installs the release and restarts the app. The Windows app
  runs the new installer silently, then reopens. A copy run from source
  downloads the new code and copies it over your copy. Open pages, including OBS sources, reload on the
  new version. Your `config.json` and everything in `data/` (leagues, logos,
  photos) are kept.
- **Later** hides the pop-up until the app is next opened. The *Update to
  vX* button in the top bar reopens it.
- **Skip this version** stops the pop-up for that version, but the next one
  will still pop up.

**Private repository**: GitHub only shows a private repository's releases
with an access token. Without one, the Updates panel says so.
1. On GitHub, go to *Settings → Developer settings → Fine-grained tokens →
   Generate*.
2. Give it this repository only, with *Contents: Read-only*.
3. Paste it into *Private repository? Add a GitHub access token* in the
   Updates panel.

The token is kept in `data/settings.json` on that PC and only sent to GitHub.
Making the repository public works too, and needs no token.

If your copy is a **git clone**, the app won't overwrite it. It tells you
to run `git pull` instead. To turn update checks off, set
`"update_check": false`.

### Publishing a new version

1. Bump `__version__` in `apex/__init__.py` (e.g. `0.3.0`).
2. Add a `## v0.3.0` section to `CHANGELOG.md`: it becomes the release notes
   shown in the pop-up.
3. Get it onto `main` (merge the pull request).

The **Release** GitHub Actions workflow sees the new version on `main` and
builds the Windows app on a Windows runner. It smoke-tests the app, builds the
installer, installs it and smoke-tests the installed copy. Then it publishes
the GitHub release with the installer and a portable zip attached. Every
running copy of the app then offers the update. Pushing a `v0.3.0` tag
yourself works too. A version that's already released is skipped.

The same Windows build runs on every pull request and branch push (**Build
Windows app**), and keeps the installer as a downloadable artifact.

### Building the Windows app yourself

```bat
pip install -r requirements.txt -r requirements-desktop.txt pyinstaller
pyinstaller packaging\apex.spec --noconfirm
"%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" /DAppVersion=0.3.0 packaging\installer.iss
```

This gives `dist\ApexCommentator\ApexCommentator.exe` and
`dist\ApexCommentator-Setup-0.3.0.exe`. `ApexCommentator.exe --smoke-test`
checks a build starts and serves its pages.

## Configuration

All keys are optional. See `config.example.json` for the full list and
defaults:

| Key | Default | Meaning |
| --- | --- | --- |
| `port` / `host` | `8180` / `127.0.0.1` | Where the overlay is served |
| `replay_preroll_s` | `6` | Seconds before the event a replay starts |
| `replay_auto_return_s` | `0` | Return to live after N seconds (0 = manual) |
| `default_camera_group` | `""` | Camera group for Watch/Replay, e.g. `"TV1"` (blank = keep current) |
| `overtake_hold_s` | `1.5` | How long a pass must hold to count |
| `slowdown_ratio` | `0.35` | Speed below this fraction of recent pace counts as a slowdown |
| `slowdown_corner_ratio` | `0.5` | ...and below this fraction of the usual speed at that point of the track |
| `spin_window_s` | `0.2` | The rotation that makes a spin must happen within this many seconds |
| `spin_yaw_deg` | `45` | Heading change in that window that counts (car driven on this PC only) |
| `spin_steer_deg` | `180` | Steering-wheel snap in that window that counts (every car) |
| `contact_jolt_kph` | `20` | Contact: how fast a car must be closing before suddenly stopping closing |
| `poll_hz` | `30` | Telemetry samples per second (spin detection needs 20 or more) |
| `event_cooldown_s` | `8` | Minimum gap between incidents logged for the same car |
| `gridwalk_interval_s` | `8` | Grid walk: seconds each pair stays on screen |
| `update_check` | `true` | Check GitHub for new versions and offer them in the app |
| `update_repo` | `"ShamzOut2/Apex_Commentator"` | Where releases are published |
| `github_token` | `""` | Only needed if that repository is private (or set `APEX_GITHUB_TOKEN`) |

## Development

```
apex/
  sources.py   iRacing (pyirsdk) and mock telemetry sources
  events.py    overtake / incident detection
  core.py      poll loop, snapshot, spectate & replay commands
  gridwalk.py  grid order and grid walk state
  laps.py      lap and sector timing for the lap tracker and standings
  overlays.py  stream overlay settings
  championship.py  championship points, drop rounds, penalties and live projection
  transfer.py  import and export (leagues, teams, championships, results, settings)
  league.py    league profiles
  server.py    stdlib HTTP server + Server-Sent Events
  updater.py   update checks and in-app updates from GitHub releases
  desktop.py   app window, single instance, message boxes, log file
  paths.py     program files vs. user data, for source and packaged app
web/           the overlay UI (plain HTML/CSS/JS, no build step)
  index.html   control panel (app.js)
  gridwalk.html  grid walk broadcast graphic for OBS (gridwalk.js)
  standings.html, laps.html  standings tower and qualifying lap tracker for OBS
  sponsors.html  sponsor logos for OBS
  driver.html  the driver on camera, for OBS
  common.js    shared helpers: logo recolouring, drawn liveries
  logos/       built-in layered class logos
packaging/     PyInstaller recipe (apex.spec) and Inno Setup installer script
assets/        app icon
tools/
  logo_to_svg.py  converts badge logos to layered SVG (dev only)
tests/
```

Run the tests with `python -m unittest discover -s tests -t .`. They need
nothing installed. The iRacing source is tested against a stand-in for
pyirsdk.
