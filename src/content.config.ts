import { defineCollection, z } from "astro:content";
import { glob } from "astro/loaders";

const pages = defineCollection({
  loader: glob({ pattern: "**/*.md", base: "./src/content/pages" }),
  schema: z.object({
    title: z.string(),
    description: z.string().optional(),
    previewImage: z.string().optional(),
    previewAlt: z.string().optional(),
    navLabel: z.string().optional(),
    isService: z.boolean().default(false),
    isLocation: z.boolean().default(false),
    city: z.string().optional(),
    state: z.string().optional(),
    population: z.number().optional(),
    order: z.number().default(999),
    omitServicePreview: z.boolean().default(false),
  }),
});

const posts = defineCollection({
  loader: glob({ pattern: "**/*.md", base: "./src/content/posts" }),
  schema: z.object({
    title: z.string(),
    description: z.string(),
    pubDate: z.coerce.date(),
    author: z.string().default("KC Pest Experts"),
    coverImage: z.string().optional(),
    coverAlt: z.string().optional(),
    /** Optional: stable id for a multi-post weekly theme (set by local-content-agent). */
    seriesTopicId: z.string().optional(),
    /** Slug of the series hub post (parts link here; hub omits or self-references). */
    seriesHubSlug: z.string().optional(),
    /** 0 = hub/overview; 1+ = supporting posts for the same seriesTopicId. */
    seriesPart: z.number().optional(),
    seriesTitle: z.string().optional(),
  }),
});

export const collections = { pages, posts };
