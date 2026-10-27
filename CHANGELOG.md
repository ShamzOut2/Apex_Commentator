# Changelog

Release notes for each version. When a version tag is pushed, its section
here becomes the GitHub release notes, which the app shows in its update
pop-up.

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
