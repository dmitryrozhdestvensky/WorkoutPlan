document.querySelector('#error-back').onclick = () => {
  if (history.length > 1 && document.referrer &&
      new URL(document.referrer).origin === location.origin) {
    history.back();
  } else {
    location.assign('/');
  }
};
