const BASE_URL = import.meta.env.VITE_API_URL;

export async function getWelcomeMessage() {
  const res = await fetch(`${BASE_URL}`);
  const data = await res.json();
  return data.message;
}
