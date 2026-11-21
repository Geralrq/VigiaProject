"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { getSupabase } from "@/shared/supabase/client";

export function useSignIn() {
  return useMutation({
    mutationFn: async ({ email, password }: { email: string; password: string }) => {
      const { error } = await getSupabase().auth.signInWithPassword({ email, password });
      if (error) throw error;
    },
  });
}

export function useSignOut() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      const { error } = await getSupabase().auth.signOut();
      if (error) throw error;
    },
    // Nada del usuario anterior debe quedar en caché.
    onSettled: () => queryClient.clear(),
  });
}

/**
 * Crea la cuenta con el nombre en los metadatos (el backend crea el perfil CIUDADANO al primer
 * ingreso). Devuelve `sessionStarted`: false si Supabase exige confirmar el correo.
 */
export function useSignUp() {
  return useMutation({
    mutationFn: async ({ name, email, password }: { name: string; email: string; password: string }) => {
      const { data, error } = await getSupabase().auth.signUp({
        email,
        password,
        options: {
          data: { full_name: name },
          emailRedirectTo: `${window.location.origin}/login`,
        },
      });
      if (error) throw error;
      return { sessionStarted: data.session !== null };
    },
  });
}

/** Pide el correo de recuperación; el enlace vuelve a /restablecer. */
export function useRequestPasswordReset() {
  return useMutation({
    mutationFn: async (email: string) => {
      const { error } = await getSupabase().auth.resetPasswordForEmail(email, {
        redirectTo: `${window.location.origin}/restablecer`,
      });
      if (error) throw error;
    },
  });
}

/** Fija la contraseña nueva y cierra la sesión de recuperación (hay que ingresar con la nueva). */
export function useUpdatePassword() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (password: string) => {
      const supabase = getSupabase();
      const { error } = await supabase.auth.updateUser({ password });
      if (error) throw error;
      await supabase.auth.signOut();
      queryClient.clear();
    },
  });
}
