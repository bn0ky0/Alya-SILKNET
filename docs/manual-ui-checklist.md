# Manual UI checklist

Run these checks in the desktop application after starting Alya SILKNET.

## Investigation graph

- Start on a fresh workspace, create one entity from the Entity page and one from the graph's **Add entity** button. Confirm the graph repaints with both cards and the app does not close.
- Add two entities, then add a directional relationship between them. Confirm the relationship card appears with a readable label and a compact, polished arrowhead that points into the target and stops just before the card border.
- Create a second named graph, add only one entity to it, move the card, then switch back to the first graph. Confirm each graph keeps its own cards and layout, and that a newly created graph starts empty.
- Rename and delete a graph workspace after confirming the prompt. Confirm every workspace, including the initial **Overview** graph, has an enabled **Delete** button. Delete the last remaining graph and confirm a new empty **Overview** workspace is created automatically.
- Drag every entity from the right-hand palette onto the canvas, use the palette search, and double-click a palette card to place it. Confirm the palette lists every workspace entity in every graph view.
- Select a node and confirm its name, type and description appear in the details panel. Confirm the panel collapses when the selection is cleared so the palette keeps its space. Confirm **Remove** removes only that graph card and leaves the entity and its relationship records in the workspace. Bring the same card back and confirm the app asks whether to restore it as **Card only** or with its previous connections.
- Double-click a node, change its name, save, and confirm the graph refreshes without moving the card or closing the app.
- Select an edge (including by clicking its relationship label) and confirm its direction, dates, claim text and verification status are visible. Delete the claim from its edit dialog, from the edge context menu, and with **Delete** / **Backspace**; confirm each route asks first and that the claim disappears while its entities and sources remain.
- Edit the selected edge, set start and end dates, and confirm the changes appear after saving.
- Drag a node, close and reopen SILKNET, and confirm the node stays where it was placed.
- Filter by a name fragment and by entity type; confirm unrelated nodes and edges are hidden.
- Use the mouse wheel to zoom and right-drag (or middle-drag) to pan across the canvas. Confirm Fit graph resets the view, the wheel stops at its zoom limits, and the page does not need vertical scrolling at the default or minimum window size.
- Connect two cards by dragging the small plus dot on a card edge, then repeat with a Shift-drag from the canvas. Confirm each opens a prefilled relationship dialog and adds an edge after saving. Confirm the toolbar has no standalone **Link** button.
- Add a detailed profile image and zoom in on the graph. Confirm the card photo stays smooth rather than blocky.
- Confirm empty graphs show a centered empty-state hint and that the entity palette still lists every entity.

## Appearance and window

- Change themes in Settings and confirm the graph colors, edge labels, selected cards and entity palette follow the selected theme.
- Move the UI scale slider from 75% to 100%; confirm text and button sizing change while window geometry, cards, graphs and spacing stay fixed. Confirm 100% is the maximum and 90% is the default.
- Confirm the app opens centered on the active monitor at a sensible size, and that resizing the window keeps the graph usable.
- On launch, confirm the branded intro fades in with the circular Alya portrait, title and progress line, then reveals the dashboard without leaving an overlay behind. Change the theme in Settings, relaunch, and confirm the backdrop, portrait ring and progress line use the new colors. Click anywhere or press `Esc`, `Space` or `Enter` to skip it, and confirm it plays again on the next launch.
- Open About and confirm the product description sits inside the Alya SILKNET card, under the version line. Confirm the update check runs once when the page opens, reports either the current version or a newer release, and that **Check for updates** runs it again. Disconnect the network and confirm the page reports a failed check without blocking the rest of the app. When a newer release is shown, confirm **Get …** opens the GitHub release page in the browser.
- Click the menu button in the top bar and press `Ctrl+B`; confirm the sidebar collapses fully and reopens with a smooth animation.
- Click every workspace tab in quick succession and confirm each page slides and fades in from the direction of the selected tab, the animation always finishes, the selected tab stays in sync and no page is left translucent. Repeat while collapsing and reopening the sidebar with the top-bar menu and `Ctrl+B`.
- In dark or light, pick each accent swatch and confirm the highlight color updates, the name label follows, and the choice persists. Confirm the swatch row hides for themes with their own palette.
- Select Alya pink and confirm the 64 px, face-only Alya-sama pet floats above the app with no disc, plate or background behind her. A thin rose silhouette rim should keep her readable on any desktop. Drag her outside the window and click her: the compact speech bubble should sit above her head with the tail pointing down to her. Move her near the top or side of the screen and confirm the bubble flips and redraws its tail rather than covering her; confirm both pet and bubble disappear in other themes. Confirm blossom petals fall over the window while the pet is active.
- Confirm the window has soft rounded corners while floating and that the corners show the desktop behind them. Maximize the window and press `F11`; confirm the chrome becomes sharp and edge-to-edge in both states, and that `Escape` leaves full screen.
- Confirm toasts appear only for important action results such as deletions, restores and imports. Startup and theme changes should stay quiet. Toasts sit above the bottom edge, disappear after a few seconds, and there is no separate status bar under the workspace.
- Drag the window by the top bar, double-click the top bar to maximize, and resize from the edges and corners. Confirm the minimize, maximize and close buttons work and are easy to read.
- Open a combo box in every theme and with every UI scale. Confirm the list is fully themed, rounded, readable and has no white native frame.
- Open the graph board selector, close it, remove most boards, then reopen it. Confirm the popup shrinks to the remaining rows, starts at the top, and never leaves a tall blank surface.
- Click the active application's taskbar button and confirm it minimizes; click it again and confirm the window restores.
- Confirm the sidebar logo has a transparent background and stays crisp at every UI scale.

## Entities, profiles and sources

- Create a person, leave **Role** blank, and confirm the record saves without a role. Edit the person, enter a role, and confirm it appears in the record list, details panel and as a floating badge above the person's graph card. Switch the type to an organization and confirm the role field hides and the saved organization has no role.
- Create a person and add a PNG or JPEG profile image. Confirm the image is copied into the local Alya SILKNET data folder and shown again when editing the person.
- Drag a PNG, JPEG, WebP or BMP file from Explorer onto the profile-image preview in the edit dialog and onto the selected record's photo placeholder in the details panel. Confirm the preview updates and the saved record shows the dropped image.
- Try an unsupported or unreadable image, including by dragging it onto a photo control, and confirm Alya SILKNET gives an error without saving the file.
- Create a social profile, choose a platform from the dropdown and enter a valid URL, then reopen the record and confirm the platform logo, username and status are retained.
- Choose Other in the platform dropdown, enter a custom platform name, and confirm the record still saves and displays correctly.
- Enter a non-HTTP URL for a social profile and confirm it is rejected.
- Delete an entity after confirming the prompt and verify its relationships disappear, the detail panel refreshes and the graph/search pages update.
- Create a source and link it from an entity and a relationship claim. Confirm Evidence & Sources lists both links and displays the claim status.
- Delete a source after confirming the prompt; verify its links are removed and the entities remain.

## Search, exchange and recovery

- Search by a name, note, tag, source title and relationship status. Open results and confirm they select the matching record in its workspace page.
- Export JSON and import it into a fresh test workspace. Confirm entities, relationship claims, sources and provenance links appear.
- Export CSV and import it into a fresh test workspace. Confirm entity names, aliases, tags and attributes are retained.
- Import the same file twice. Confirm duplicates are listed in the preview and skipped.
- Try a malformed JSON or CSV file and confirm no records are added.
- Create a ZIP backup, change a record, restore the backup and confirm the old record and profile image return. Confirm a safety backup is created before restore.
- Switch among all appearance options and confirm the selected theme, accent and UI scale persist after restarting Alya SILKNET.

## Windows release

- Run `scripts/build_windows.ps1` and confirm the complete `dist/SILKNET` folder is created with `SILKNET.exe`, the Alya icon, logo and bundled fonts.
- Launch `dist/SILKNET/SILKNET.exe` with temporary `SILKNET_CONFIG_DIR` and `SILKNET_DATA_DIR` values. Confirm the window opens, a database and log are created, and the existing local workspace is unchanged.
- With the app still open, launch `SILKNET.exe` again. Confirm no second window appears and the existing window is restored, unminimized and brought to the front.
- Run `scripts/build_installer.ps1` and confirm `dist/installer/installer.exe` is created. Install it for the current user, confirm the Start Menu shortcut launches the app, then uninstall it and confirm the installed files and shortcuts are removed.

