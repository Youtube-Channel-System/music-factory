# Privacy Policy — FOCUS & CO engine

FOCUS & CO engine is a private automation that uploads the owner's own original music videos to the owner's own YouTube channel (FOCUS & CO, @focusndco). It has a single user: the channel owner. It is not distributed and does not access anyone else's account.

## YouTube API Services
This application uses YouTube API Services. By using it, the owner is bound by the [YouTube Terms of Service](https://www.youtube.com/t/terms) and the [Google Privacy Policy](https://policies.google.com/privacy).

## What it accesses and why
- **Scope:** `https://www.googleapis.com/auth/youtube`, only for the owner's own channel.
- **Used for:** uploading videos and Shorts, setting thumbnails, scheduling publication, changing a video's privacy status after the owner approves it, and adding videos to the owner's own playlists.
- **Read access:** the status of the owner's own uploads and the owner's own playlists.

## What it stores
- The OAuth refresh token, as an encrypted GitHub Actions secret owned by the channel owner.
- The IDs, titles and publication times of the videos the tool uploaded (a history file in the owner's private repository).
- It does not collect, store, sell or share personal data of any other person, and does not use YouTube data for advertising.
- Data obtained through YouTube API Services is not kept beyond the owner's own upload history.

## Revoking access and deleting data
The owner can revoke the application's access at any time at https://myaccount.google.com/permissions (or https://security.google.com/settings/security/permissions). Deleting the repository secret and history file removes all data the application holds.

## Google API Services User Data Policy
Use of information received from Google APIs adheres to the [Google API Services User Data Policy](https://developers.google.com/terms/api-services-user-data-policy), including the Limited Use requirements.

Contact: open an issue at https://github.com/Youtube-Channel-System/music-factory/issues
