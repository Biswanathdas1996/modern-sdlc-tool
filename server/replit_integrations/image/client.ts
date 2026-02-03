import { Buffer } from "node:buffer";

/**
 * Image generation is not supported with PWC GenAI.
 * This module is disabled. Use an external image generation service if needed.
 */

/**
 * Generate an image and return as Buffer.
 * @deprecated PWC GenAI does not support image generation
 */
export async function generateImageBuffer(
  prompt: string,
  size: "1024x1024" | "512x512" | "256x256" = "1024x1024"
): Promise<Buffer> {
  throw new Error(
    "Image generation is not supported. PWC GenAI only supports text generation. " +
    "Please use an external image generation service if needed."
  );
}

/**
 * Edit/combine multiple images into a composite.
 * @deprecated PWC GenAI does not support image editing
 */
export async function editImages(
  imageFiles: string[],
  prompt: string,
  outputPath?: string
): Promise<Buffer> {
  throw new Error(
    "Image editing is not supported. PWC GenAI only supports text generation. " +
    "Please use an external image editing service if needed."
  );
}

