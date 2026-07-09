-- 0005_profile_trigger.sql
-- Auto-create a user_profiles row when a new auth.users record is inserted (first login).
-- SECURITY DEFINER so it can insert into user_profiles regardless of the caller's RLS.
-- display_name is NOT NULL, so we derive a sensible default from metadata or the email local-part.

create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into public.user_profiles (id, display_name)
  values (
    new.id,
    coalesce(
      nullif(new.raw_user_meta_data->>'display_name', ''),
      split_part(new.email, '@', 1)
    )
  )
  on conflict (id) do nothing;
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;

create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();
