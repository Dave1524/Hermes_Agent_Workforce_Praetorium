// Minimal Praetorium test bot (NUC-13): replies when mentioned. Parked until
// DISCORD_BOT_TOKEN exists in secrets.env. Rule: no client-identifiable content
// in Discord — this bot only ever emits status strings.
import { Client, GatewayIntentBits } from "discord.js";

const token = process.env.DISCORD_BOT_TOKEN;
if (!token) {
  console.log("BLOCKED: DISCORD_BOT_TOKEN empty — bot not started (by design)");
  process.exit(0);
}

const client = new Client({
  intents: [GatewayIntentBits.Guilds, GatewayIntentBits.GuildMessages, GatewayIntentBits.MessageContent],
});

client.on("clientReady", () => console.log(`logged in as ${client.user.tag}`));
client.on("messageCreate", async (msg) => {
  if (msg.author.bot) return;
  if (msg.mentions.has(client.user)) {
    await msg.reply("PRAETORIUM-OK — reporting for duty.");
  }
});

client.login(token);
