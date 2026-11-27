// The film strip of a video being made (design bar: "you watch it being made"): one tile per planned scene, finished scenes filled (with their picture when the server has one),
// the scene in work ringed, the rest outlined. Decorative: the words beside it carry the meaning for a screen reader.
import { useState } from "react";
import type { StripTile } from "../../lib/videos";

function Tile({ tile }: { tile: StripTile }) {
  const [broken, setBroken] = useState(false);   // an expired or missing picture falls back to the plain filled tile
  return (
    <li className={`strip-tile is-${tile.state}`}>
      {tile.thumb && !broken && <img src={tile.thumb} alt="" decoding="async" onError={() => setBroken(true)} />}
    </li>
  );
}

export default function FilmStrip({ tiles, className = "" }: { tiles: StripTile[]; className?: string }) {
  if (!tiles.length) return null;
  return <ol className={`strip ${tiles.length > 12 ? "is-dense" : ""} ${className}`} aria-hidden="true" data-count={tiles.length}>{tiles.map((t) => <Tile key={t.index} tile={t} />)}</ol>;
}
