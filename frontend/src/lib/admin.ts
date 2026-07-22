import { apiFetch } from "@/lib/api"

export interface Me {
  user_id: string
  email: string | null
  is_admin: boolean
}

export interface Member {
  email: string
  password_set: boolean
  created_at: string | null
}

/** Current user, including whether they are the admin (drives admin-only UI). */
export async function getMe(): Promise<Me> {
  return (await apiFetch("/api/me")) as Me
}

/** All members (admin only). */
export async function listMembers(): Promise<Member[]> {
  return (await apiFetch("/api/admin/members")) as Member[]
}

/** Invite a member by email (admin only). Returns the created member. */
export async function inviteMember(email: string): Promise<Member> {
  return (await apiFetch("/api/admin/invite", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email }),
  })) as Member
}
