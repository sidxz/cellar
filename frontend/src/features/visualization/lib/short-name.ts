/** ``name`` in at most ``max`` characters, cut in the middle: protocol names follow "subject
 * + measurement [method on collision]", so their tail is what tells them apart. A trailing
 * "[…]" is kept whole when it leaves the head room; else the tail takes half. */
export function shortName(name: string, max = 32): string {
  if (name.length <= max) return name;
  const method = /\[[^\]]*\]$/.exec(name)?.[0];
  const tail =
    method && method.length <= max - 9 ? method : name.slice(-Math.ceil((max - 1) / 2)).trimStart();
  return `${name.slice(0, max - 1 - tail.length).trimEnd()}…${tail}`;
}
