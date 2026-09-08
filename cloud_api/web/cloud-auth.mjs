import { firebaseConfig } from './firebase-config.mjs';

// Loaded only when cloud mode is explicitly requested. Offline pairing stays separate.
async function loadFirebase() {
  const [app, auth] = await Promise.all([
    import('https://www.gstatic.com/firebasejs/12.18.0/firebase-app.js'),
    import('https://www.gstatic.com/firebasejs/12.18.0/firebase-auth.js'),
  ]);
  return { ...app, ...auth };
}

export function createCloudAuth(loadSdk = loadFirebase, initializationTimeoutMs = 15000) {
  let initialization;
  async function ready() {
    if (!initialization) {
      const loading = (async () => {
        const sdk = await loadSdk();
        const existing = sdk.getApps().find(app => app.name === 'linguafusion-cloud');
        const app = existing || sdk.initializeApp(firebaseConfig, 'linguafusion-cloud');
        const auth = sdk.getAuth(app);
        await auth.authStateReady();
        return { sdk, auth };
      })();
      let timer;
      const deadline = new Promise((_, reject) => {
        timer = setTimeout(() => reject(new Error('Initialization timeout')), initializationTimeoutMs);
      });
      initialization = Promise.race([loading, deadline]).finally(() => clearTimeout(timer)).catch(() => {
        initialization = undefined;
        throw new Error('Cloud sign-in could not load. Check your connection and retry.');
      });
    }
    return initialization;
  }

  return Object.freeze({
    async observe(listener) {
      const { sdk, auth } = await ready();
      return sdk.onAuthStateChanged(auth, user => listener(
        user ? { uid: user.uid, email: user.email, emailVerified: user.emailVerified === true } : null));
    },
    async signIn(email, password, remember = false) {
      if (typeof email !== 'string' || !email.trim() || typeof password !== 'string' || !password) {
        throw new Error('Enter your email and password.');
      }
      const { sdk, auth } = await ready();
      try {
        await sdk.setPersistence(auth, remember ? sdk.browserLocalPersistence : sdk.browserSessionPersistence);
        const result = await sdk.signInWithEmailAndPassword(auth, email.trim(), password);
        // UI gets identity only. No password/token is stored by this adapter.
        return { uid: result.user.uid, email: result.user.email };
      } catch {
        throw new Error('Unable to sign in. Check your details and connection, then try again.');
      }
    },
    async signUp(email, password, remember = false) {
      if (typeof email !== 'string' || !email.trim()) throw new Error('Enter your email address.');
      if (typeof password !== 'string' || password.length < 8) {
        throw new Error('Choose a password of at least 8 characters.');
      }
      const { sdk, auth } = await ready();
      try {
        await sdk.setPersistence(auth, remember ? sdk.browserLocalPersistence : sdk.browserSessionPersistence);
        const result = await sdk.createUserWithEmailAndPassword(auth, email.trim(), password);
        await sdk.sendEmailVerification(result.user);
        return { uid: result.user.uid, email: result.user.email, emailVerified: false };
      } catch (error) {
        // Distinguish only the case the person can act on; never echo provider detail.
        if (error?.code === 'auth/email-already-in-use') {
          throw new Error('That address already has an account. Sign in instead.');
        }
        if (error?.code === 'auth/weak-password') throw new Error('Choose a longer, less common password.');
        if (error?.code === 'auth/invalid-email') throw new Error('That email address is not valid.');
        throw new Error('Could not create the account. Check your details and connection, then retry.');
      }
    },

    async sendVerification() {
      const { sdk, auth } = await ready();
      if (!auth.currentUser) throw new Error('Sign in first.');
      try {
        await sdk.sendEmailVerification(auth.currentUser);
      } catch {
        throw new Error('Could not send the confirmation email. Wait a moment and try again.');
      }
    },

    async refreshVerification() {
      // Firebase caches emailVerified on the client, so a fresh read is needed
      // after the person clicks the link in another tab or on another device.
      const { auth } = await ready();
      if (!auth.currentUser) return false;
      await auth.currentUser.reload();
      if (auth.currentUser.emailVerified) await auth.currentUser.getIdToken(true);
      return auth.currentUser.emailVerified === true;
    },

    async signOut() {
      const { sdk, auth } = await ready();
      await sdk.signOut(auth);
    },
    async authorizationHeader() {
      const { auth } = await ready();
      const user = auth.currentUser;
      if (!user) throw new Error('Sign in to use cloud mode.');
      try {
        const token = await user.getIdToken();
        if (auth.currentUser !== user) throw new Error('Session changed.');
        return { Authorization: `Bearer ${token}` };
      } catch {
        throw new Error('Your cloud session could not be refreshed. Sign in again.');
      }
    },
  });
}
