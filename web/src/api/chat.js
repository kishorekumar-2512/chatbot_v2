import { post, postStream, postDownload } from './client.js';

/**
 * Send a chat question (non-streaming). Returns the full ChatResponse.
 */
export async function sendChat(question, context = null, orgId = null) {
  return post('/chat', { question, context, org_id: orgId });
}

/**
 * Send a chat question with SSE streaming. Returns the raw Response.
 */
export async function sendChatStream(question, context = null, orgId = null, imageBase64 = null) {
  return postStream('/chat/stream', { question, context, org_id: orgId, image_base64: imageBase64 });
}

/**
 * Run user-edited SQL directly.
 */
export async function runSQL(sql, question = '') {
  return post('/run-sql', { sql, question });
}

/**
 * Send 👍/👎 feedback.
 */
export async function sendFeedback(data) {
  return post('/feedback', data);
}

/**
 * Generate and download a PDF report.
 */
export async function downloadPDF(data) {
  const blob = await postDownload('/report/pdf', data);
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `report_${Date.now()}.pdf`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
