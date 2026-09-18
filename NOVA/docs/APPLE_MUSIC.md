# Apple Music Integration

NOVA and Lumi can control the macOS Music app through chat and voice. The desktop Core page displays the current title, artist, album, native artwork when available, position, and playback state. Previous, pause/resume, and next controls use confirmed Music responses.

## Setup

1. Open Music and sign in to your Apple account. Make sure requested songs and playlists are added to your library and are playable in Music. Subscription tracks require an active subscription and appropriate library synchronization.
2. Restart the NOVA backend yourself after installing these changes, then refresh the desktop at http://localhost:1420.
3. Allow your backend host application to control Music if macOS asks. Review this under System Settings > Privacy & Security > Automation. Do not enter account credentials into chat.
4. Enable voice and hands-free wake only when you want microphone capture. Nova and Lumi are both supported wake names.

## Requests

- "Play music", "play Apple Music", or "start music": resumes Music's last playback context without searching the library. This can resume a catalog track already opened in Music. Playback must be confirmed by the app; an empty playback context is not treated as success.
- "Hey Lumi, play something" or "play soothing music": chooses a random library track tagged ambient, classical, meditation, or relaxation, or a track from a soothing, calm, relaxing, or ambient-named playlist.
- "Play Hello by Adele": searches title, then checks artist credits. Titles can match catalog suffixes or versions in the library.
- "Play Adele songs" or "play songs by Adele": chooses from matching artist credits in the library.
- "Play playlist Relax": chooses a track from the named library playlist. This does not promise to replace the entire upcoming queue with that playlist.
- "Play jazz music": selects matching library genres. Classical, ambient, pop, rock, instrumental, meditation, country, electronic, and blues are also recognized.
- "Pause music", "resume music", "next song", and "previous track": control the Music app.

If no suitable match exists, NOVA asks for a song, artist, playlist, or genre. A short reply such as "Adele" or "jazz" is treated as a selection only when the immediately preceding assistant response was that music-choice question. Questions and cancellation replies are not interpreted as selections. This uses the application's existing in-session conversation history, not a separate persistent preference store.

Voice wake detection remains enabled during music if hands-free mode is on. A successful music action closes the active conversation window so another wake phrase is needed. An unsuccessful selection keeps it open for your reply. Speaker audio can still cause transcription errors or false wake events; test with a headset first.

## Limits

- This implementation searches the Music app's library, not the entire Apple Music catalog. Arbitrary catalog streaming requires a separately authorized MusicKit integration with developer and user authorization. It is not implemented here. A missing title is reported rather than silently replaced by unrelated music or a preview.
- Add a soothing playlist to your library for predictable "play something" selections. Selection uses existing genre and playlist metadata, not acoustic mood analysis or learned personal taste.
- Artwork is read from the current track, validated as JPEG/PNG, capped at 2 MB, and cached in memory for the current track. Missing artwork has a neutral fallback; no external image search or file persistence is used.
- Native commands have timeouts and are serialized. A successful command must also have a matching playback state; selecting a song additionally checks the current track ID. A delayed or unavailable state is reported as unconfirmed.
- No MusicKit token, account credential, library mutation, or automatic library download is configured by this integration.

## API And Verification

`GET /api/music/status` and `POST /api/music/control` are restricted to loopback requests and allowed desktop origins. Control operations are `pause`, `resume`, `next`, and `previous`; arbitrary scripts are not accepted. Responses disable caching. Queries are passed as native process arguments, never inserted into executable JavaScript.

Verified on 2026-09-10: read-only native status, real JPEG artwork extraction, matching an existing library song and artist, and empty-result genre/playlist/soothing searches. The read-only search probes replaced the playback statement with a result return. No live playback control, microphone capture, main-backend restart, or library edit was performed by the assistant.

Automated checks: 31 music tests; 118 combined music/wake/conversation/TTS tests; 56 desktop tests. Browser checks used simulated metadata and control responses at 1440x1000 and 390x844, with no player overflow. Native artwork extraction was checked separately. The existing 59 TypeScript errors still block a clean production build.

## Player Refresh And Reconnection

Updated 2026-09-10 after a report of an old-fashioned player and repeated connection warnings:

- Core now uses larger artwork, separate title/artist/album lines, circular transport controls and a themed timeline. Progress advances between confirmed samples for at most five seconds and freezes when status is stale. Mobile Core grows with its content so the player and chat do not overlap Overview.
- A failed status refresh no longer removes the last confirmed track or artwork. They remain explicitly labeled as the last known track while reconnecting, with controls disabled until a fresh status arrives. A confirmed stopped state still clears the track normally.
- Connection errors distinguish an unreachable backend, a timeout, denied local access (403), and a missing music endpoint (404, requiring a backend reload). These diagnostics do not imply that the Music app has stopped playing.
- The live endpoint and browser fetch both returned HTTP 200 with actual track metadata and artwork during investigation. A persistent backend failure was not reproduced. An intentionally dropped browser status request verified artwork retention, stale-control disabling and automatic recovery on the next successful poll; the request interception was removed afterward.
- Verification: all 65 desktop tests pass, including reconnection and error diagnostics. Desktop/mobile screenshots use actual native artwork, with a loaded 600-pixel image, checked transport-icon contrast and no player overflow. The existing 59 TypeScript errors remain. Backend code and lifecycle were not changed; no playback command was issued.