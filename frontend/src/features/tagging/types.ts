import type { AssignTagBody, EntityTagResponse, TagResponse } from "@/shared/lib/api/model";

/** URL collection segment for a taggable entity (frontend routing concept). */
export type TaggableEntity = "molecules" | "protocols" | "projects" | "collections";

/** A workspace tag (key + optional value). Alias of the generated API type. */
export type Tag = TagResponse;

/** A tag on an entity, plus assignment provenance. Alias of the generated API type. */
export type EntityTag = EntityTagResponse;

/** Payload to create/assign a tag on an entity. Alias of the generated API type. */
export type TagInput = AssignTagBody;
