import { encryptPV1, decryptPV1, publicKeyOf } from "./src/shared/pv1.js";
import { deriveAgentKey } from "./src/shared/agentkeys.js";
import { keccak256, toUtf8Bytes, Wallet } from "ethers";
import fs from "fs";
const wallet = "0x" + "11".repeat(32);
const agent = deriveAgentKey(wallet, 1);
const texts = ["hi", "Eddie prefers mint green. 🌿 — ünïcödé", "x".repeat(1800), JSON.stringify({ title: "t", body: "b\nc" })];
const vec = { agentPriv: agent.privateKey, agentPub: agent.publicKey, agentAddress: agent.address, cards: [] };
for (const t of texts) vec.cards.push({ plain: t, pv1: await encryptPV1(t, agent.publicKey) });
const transport = Wallet.createRandom();
vec.transportPriv = transport.privateKey;
vec.keyForAgent = await encryptPV1(agent.privateKey, publicKeyOf(transport.privateKey));
vec.keccak = texts.map((t) => keccak256(toUtf8Bytes(t)));
if (process.argv[2]) { // verify python-made ciphertexts
  const py = JSON.parse(fs.readFileSync(process.argv[2]));
  for (const c of py) { const p = await decryptPV1(c.pv1, agent.privateKey); if (p !== c.plain) throw new Error("mismatch"); }
  console.log("JS opened", py.length, "python cards");
} else fs.writeFileSync("/app/conversations/6a68444d4bc0607c4852d152/hermes-plugin/brainvault/tests/pv1_vectors.json", JSON.stringify(vec, null, 1));
