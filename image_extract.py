import os
import sys
import fitz  # pip install --upgrade pip; pip install --upgrade pymupdf
from tqdm import tqdm # pip install tqdm
import requests
from bs4 import BeautifulSoup
import urllib
import requests
import csv
import shutil
import validators
from dotenv import load_dotenv
import time
from document_extract import classify_single_pdf
load_dotenv("C:\\Users\\xiaog\\Desktop\\stuff\\fall24\\urop\\headers.env")

# change cookies if breaks
headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:131.0) Gecko/20100101 Firefox/131.0',
           'Cookie' : 'aws-waf-token=' + os.environ['AWS_WAF_TOKEN']}


def extract_image_from_pdf(workdir, path):
    """
    Extracts all images from a given pdf ( workdir/path(.pdf) ) and saves them in a folder under workdir/path 

    workdir: working directory
    path: folder name
    """
    doc = fitz.Document((os.path.join(workdir, path)))
    newdir = path.rsplit('.', 1)[0]
    os.mkdir(os.path.join(workdir, newdir))
    for i in tqdm(range(len(doc)), desc="pages"):
        for img in tqdm(doc.get_page_images(i), desc="page_images"):
            xref = img[0]
            pix = fitz.Pixmap(doc, xref)
            if pix.width < 150 or pix.height < 150:      # eliminate extraneous images; also consider that some are full length screenshots
                continue

            ## TODO: figure out plantiff/defendant and label as such
            pix.save(os.path.join(workdir, newdir, "%s_p%s-%s.png" % (path[:-4], i, xref)))

def extract_img(workdir):
    """
    Extracts all images from all pdfs contained directly in workdir

    workdir: the working directory
    """
    for path in os.listdir(workdir):
        if ".pdf" in path:
            extract_image_from_pdf(workdir, path)
    return


def download_pdf(url, workdir, model=None):
    """
    Downloads the pdf that the URL points to in the working directory

    url: the URL which contains the PDF
    workdir: the working directory the PDF will be downloaded to
    """
    while True:
        try:
            response = urllib.request.urlopen(url)

            test = url.split('/')
            file = open(os.path.join(workdir, test[-1]), 'wb')
            file.write(response.read())
            file.close()

            if model is not None:
                if classify_single_pdf(workdir, test[-1], model) == "other":
                    os.remove(os.path.join(workdir, test[-1]))
            break
        except Exception as e:
            if "429" in str(e):
                time.sleep(60)
            else:
                print(url + " could not be downloaded due to the following error: " + str(e))
                break
    return

# deletes empty folders
def clean(workdir):
    """
    Deletes all empty folders located directly in a working directory

    workdir: working directory
    """
    folders = list(os.walk(workdir))[1:]

    for folder in folders:
        # folder example: ('FOLDER/3', [], ['file'])
        if not folder[2]:
            os.rmdir(folder[0])
    return

# COURTLISTENER ONLY ATM
def extract_from_url(url, workdir, model=None):
    """
    Extracts all pdfs and images within a given **courtlistener** URL.

    TODO:
    - add support for non-courtlistener URLs

    url: URL where pdfs are linked to
    workdir: working directory
    """
    if "courtlistener" in url:
        try:
            pdfs = set()

            original_url = url
            # print(soup)
            while True:
                try:
                    read = requests.get(url, headers=headers)

                    # print(read.status_code)
                    html_content = read.content
                    soup = BeautifulSoup(html_content, "html.parser")
                    v = soup.find('div', id='docket-entry-table')
                    # print(v)

                    for link in v.find_all('a', {}):
                        # print(link.attrs.get('href', 'Not found'))
                        if link.attrs.get('href', 'Not found').find('storage.courtlistener.com') != -1:
                            # print(link.attrs.get('href', 'Not found'))
                            # html_for_pdf = requests.get(url + link.get('href')).content
                            # soup_for_pdf = BeautifulSoup(html_for_pdf, "html.parser")
                            # for tot in soup_for_pdf.find_all('object', type="application/pdf"):
                            #     s = tot.get('data')
                            #     # eh not sure if this works, test later
                            #     if s.find("pdf") != -1:
                            #         pdfs.add(s)
                            pdfs.add(link.attrs.get('href'))
                    # break
                    
                    if not soup.find('a', rel='next'):
                        break
                    elif soup.find('a', rel='next').attrs.get('href') != "#":
                        url = original_url + soup.find('a', rel='next').attrs.get('href')
                    else:
                        break
                except Exception as e:
                    print(e)
                    if "429" in str(e):
                        time.sleep(60)
                    else:
                        break

            print("Parsed!")

            for pdf in tqdm(pdfs):
                download_pdf(pdf, workdir, model)
                # print("Downloaded " + str(cnt) + " out of " + str(len(pdfs)))
        except Exception as e:
            print(url + " || Download failed: " + str(e))
            with open(os.path.join(workdir, "unextracted_files.txt"), 'a') as f:
                f.write(url + '\n')
    else:
        print("Not a courtlistener docket")
        
    return

def extract(url, workdir, model=None, pdf_extract=True, img_extract=True):
    """
    Given a URL, creates the necessary folders/deletes any previous folders with the same name to 
    download pdfs/images from the URL and deletes any folders that are created which do not 
    contain any content.

    url: URL to be parsed
    workdir: working directory
    """
    prv = workdir
    if "courtlistener" not in url:
        print(url + " ERROR: type not supported")
        with open(os.path.join(workdir, "unextracted_urls.txt"), 'a') as f:
            f.write(url + '\n')
        return
    try:
        print("Extracting " + url + "...")
        if not validators.url(url):
            return
        split_url = url.split('/')
        dir_name = (split_url[-1] if split_url[-1] != "" else split_url[-2]) + "\\"

        workdir += "\\" + dir_name
        # print(workdir)
        
        if pdf_extract:
            if os.path.exists(workdir):
                # If the folder exists, delete it
                shutil.rmtree(workdir)
            os.mkdir(workdir)
            print("Directory created")
            extract_from_url(url, workdir, model)
        
        if img_extract:
            extract_img(workdir)
        clean(workdir)
    except Exception as e:
        print(url + " ERROR " + str(e))
        with open(os.path.join(prv, "unextracted_urls.txt"), 'a') as f:
            f.write(url + '\n')

def read_csv(filename, workdir, model=None, pdf_extract=True, img_extract=True):
    """
    Given a .csv file, extracts all images/pdfs from each of the links within the csv within their own folders.

    workdir: working directory
    filename: .csv file
    """
    file = open(os.path.join(workdir, filename), "r")
    reader = csv.reader(file, delimiter=',')
    print("Currently on || " + workdir + "/" + filename)
    for row in reader:
        # print("extracting " + column + "...")
        extract(row[0], workdir, model, pdf_extract, img_extract)
    return

def read_all_csvs(workdir):
    """
    Given a working directory, extracts all pdfs and images from links contained within all .csv files.
    """
    filenames = os.listdir(workdir)
    for filename in filenames:
        if filename.endswith(".csv"):
            # numFiles.append(fileNames)
            print("Opening " + filename + "...")
            read_csv(filename, workdir)
    return

def main():
    workdir = "C:\\Users\\xiaog\\Desktop\\stuff\\fall24\\urop"
    # read_csv("test.csv", workdir)
    # print(urls_read)

    # extract("https://www.courtlistener.com/docket/16696071/francesca-gregorini-v-apple-inc/", workdir, True, False)

    return 0

if __name__ == '__main__':
    sys.exit(main())