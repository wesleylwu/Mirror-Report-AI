import NavBar from "../components/NavBar";
import Mirror from "../components/Mirror";
import Footer from "../components/Footer";

const Page = () => {
  return (
    <div className="bg-mirror-white flex min-h-screen flex-col">
      <NavBar />
      <Mirror />
      <Footer />
    </div>
  );
};

export default Page;
