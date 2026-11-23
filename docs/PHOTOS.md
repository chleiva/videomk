# Your own photos in a video (first slice, 2026-11-23)

Up to **10 photos** per video. In the app: tap the photo button in the composer (system photo picker: no permission prompt, the app only gets the photos
you tap), say what the video should be about, send. The row in the list shows the upload, then the usual progress, then the video.

## Flow
1. **Phone** (`PhotoPrep`): each photo is made upright, at most 2048 px on its longest side, and re-encoded with **no metadata at all** (no GPS, camera or date). Tested with real EXIF/GPS.
2. **Upload** (`POST /users/{u}/uploads`, then S3): one presigned POST per photo, pinned to one key in the user's own folder (`uploads/<user>/<id>.jpg`), `image/jpeg`, at most 10 MB (S3 itself refuses more, tested live). The login token is never sent to storage. 150 photos per user per day.
3. **Request**: `POST .../generate` with `media: [ids]`. The launcher checks every id is well formed and really exists in the caller's folder before anything is charged. Credits are unchanged (1 per started minute).
4. **Engine** (`engine/usermedia.py`): re-reads each upload, rejects anything that is not a photo (GIF, bomb, tiny, unreadable), rotates by the orientation tag, strips everything, writes a clean copy under `generation/v2/<video>/assets/user_P<n>.jpg`, **deletes the original**, and makes one batched call to a small vision model for a caption and a safety verdict per photo.
5. **Script**: the director gets the photo list (caption, orientation, date taken) and must use every photo, in date order when known, narrating what is visible and what the brief says, inventing no names, places or events. A missing photo triggers one retry and then a plain scene for it: a photo is never dropped.
6. **Render**: an `image` scene with `props.photo`; landscape photos fill the frame, portrait and square photos are shown whole over a dark blurred copy of themselves (never a face cropped off).

## Safety and privacy
- Safety review (`PHOTO_REVIEW=on|log_only|off`): nudity, graphic violence, identity documents / bank cards / screens with personal data, hate symbols are left out (the video is made from the rest; if none is usable the request is declined with a reason). Ordinary photos of people, children, family and pets are fine. A failed review never blocks a video. It is a cheap filter, not a legal safeguard.
- Photos go only to Bedrock inside our AWS account. Originals are deleted as soon as the clean copy exists (a lifecycle rule removes any leftover after 2 days). The clean copies stay with the video (editing needs them) and must be deleted with the video and with the account (account deletion is still to build).
- The privacy policy must say: photos are processed by an AI model to write and make the video, location data is removed, originals are deleted, copies are kept with the video until it is deleted.

## Not built yet
Replacing a photo in the editor, per-photo notes ("this is Grandma"), more than 10 photos (needs batching and smarter selection), video clips, Live Photo motion, HEIC is handled by the phone (ImageIO) but untested on a real device, free-tier photo caps (5 per video), account deletion of photos.
