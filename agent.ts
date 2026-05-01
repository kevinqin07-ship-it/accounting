// agent.ts — Vercel AI SDK + Composio

import { anthropic } from "@ai-sdk/anthropic";
import { Composio } from "@composio/core";
import { VercelProvider } from "@composio/vercel";
import { stepCountIs, streamText } from "ai";

const composio = new Composio({ provider: new VercelProvider() });
const userId = "user_zfc5kk";

// Create a tool router session
const session = await composio.create(userId);
const tools = await session.tools();

const stream = await streamText({
  model: anthropic("claude-sonnet-4-6"),
  prompt: "Star the composiohq/composio repo on GitHub",
  stopWhen: stepCountIs(10),
  tools,
});

for await (const textPart of stream.textStream) {
  process.stdout.write(textPart);
}
